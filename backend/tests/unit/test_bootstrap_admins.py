"""Unit tests for the startup bootstrap-admin sweep (app.services.bootstrap_admins)."""

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services import bootstrap_admins
from app.services.bootstrap_admins import elevate_bootstrap_admins

_MOD = "app.services.bootstrap_admins"


def _user(email: str, role: str | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.role = role
    return user


def _factory_yielding(session: AsyncMock) -> MagicMock:
    """A stand-in for ``async_session_factory`` whose context yields ``session``."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


def _repo_returning(users: list[MagicMock]) -> MagicMock:
    repo = MagicMock()
    repo.get_by_emails = AsyncMock(return_value=users)
    return repo


class TestElevateBootstrapAdmins:
    async def test_empty_list_opens_no_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "")
        with (
            patch(f"{_MOD}.async_session_factory") as factory,
            patch(f"{_MOD}.UserRepository") as repo_cls,
        ):
            assert await elevate_bootstrap_admins() == 0
        factory.assert_not_called()
        repo_cls.assert_not_called()

    async def test_owned_session_is_committed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "admin@x.com")
        session = AsyncMock()
        user = _user("admin@x.com")
        with (
            patch(f"{_MOD}.async_session_factory", _factory_yielding(session)),
            patch(f"{_MOD}.UserRepository", return_value=_repo_returning([user])),
        ):
            assert await elevate_bootstrap_admins() == 1
        assert user.role == "pmo_manager"
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_provided_session_is_flushed_not_committed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "admin@x.com")
        session = AsyncMock()
        with (
            patch(f"{_MOD}.async_session_factory") as factory,
            patch(
                f"{_MOD}.UserRepository",
                return_value=_repo_returning([_user("admin@x.com")]),
            ),
        ):
            assert await elevate_bootstrap_admins(session) == 1
        factory.assert_not_called()
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_counts_only_rows_that_changed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "one@x.com, two@x.com")
        session = AsyncMock()
        fresh = _user("one@x.com")
        already = _user("two@x.com", role="pmo_manager")
        with patch(
            f"{_MOD}.UserRepository", return_value=_repo_returning([fresh, already])
        ):
            assert await elevate_bootstrap_admins(session) == 1
        assert fresh.role == "pmo_manager"
        assert already.role == "pmo_manager"

    async def test_no_flush_when_nothing_changed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "admin@x.com")
        session = AsyncMock()
        with patch(
            f"{_MOD}.UserRepository",
            return_value=_repo_returning([_user("admin@x.com", role="pmo_manager")]),
        ):
            assert await elevate_bootstrap_admins(session) == 0
        session.flush.assert_not_awaited()

    async def test_logs_a_listed_email_that_has_no_row(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Not an error: the row is elevated when that person first signs in.
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "Nobody@X.com")
        session = AsyncMock()
        with (
            patch(f"{_MOD}.UserRepository", return_value=_repo_returning([])),
            caplog.at_level(logging.INFO, logger=bootstrap_admins.logger.name),
        ):
            assert await elevate_bootstrap_admins(session) == 0
        assert any(
            "no user row yet: email=nobody@x.com" in r.message for r in caplog.records
        )
