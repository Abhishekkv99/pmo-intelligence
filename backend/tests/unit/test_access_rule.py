"""Unit tests for the access rule: an active user with a known role, or nothing.

Covers ``may_use_app`` / ``assert_may_sign_in`` and the per-request check in
``get_current_user`` (the integration suite replaces that dependency).
"""

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dependencies import get_current_user
from app.services.auth_service import SESSION_ENDED_MESSAGE, AuthService
from app.utils.entitlements import (
    NO_ACCESS_MESSAGE,
    assert_may_sign_in,
    may_use_app,
)
from app.utils.exceptions import AuthenticationError, AuthorizationError


def _user(role: str | None = "sme", active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.is_active = active
    return user


class TestMayUseApp:
    @pytest.mark.parametrize("role", ["pmo_manager", "sme", "tech_lead", "ps", "admin"])
    def test_active_user_with_a_known_role(self, role: str) -> None:
        assert may_use_app(_user(role=role))

    @pytest.mark.parametrize(
        ("role", "active"), [(None, True), ("superuser", True), ("sme", False)]
    )
    def test_no_role_unknown_role_or_disabled(
        self, role: str | None, active: bool
    ) -> None:
        assert not may_use_app(_user(role=role, active=active))


class TestAssertMaySignIn:
    def test_returns_the_user_who_may(self) -> None:
        user = _user()
        assert assert_may_sign_in(user, account="a@co.com", via="sso") is user

    def test_no_user_is_refused_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="app.utils.entitlements"),
            pytest.raises(AuthorizationError) as exc_info,
        ):
            assert_may_sign_in(None, account="who@co.com", via="sso")

        assert exc_info.value.message == NO_ACCESS_MESSAGE
        assert exc_info.value.status_code == 403
        assert "via=sso account=who@co.com user_id=None" in caplog.text


class TestGetCurrentUser:
    async def _resolve(self, user: MagicMock | None) -> object:
        request = MagicMock()
        request.url.path = "/api/v1/auth/me"
        with (
            patch.object(AuthService, "decode_access_token", return_value=uuid.uuid4()),
            patch(
                "app.dependencies.UserRepository.get_by_id",
                new=AsyncMock(return_value=user),
            ),
        ):
            return await get_current_user(request, token="t", db=AsyncMock())

    async def test_user_with_a_role_passes(self) -> None:
        user = _user(role="ps")
        assert await self._resolve(user) is user

    @pytest.mark.parametrize(("role", "active"), [(None, True), ("ps", False)])
    async def test_role_removed_or_disabled_is_refused(
        self, role: str | None, active: bool, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            caplog.at_level(logging.WARNING, logger="app.dependencies"),
            pytest.raises(AuthenticationError, match=SESSION_ENDED_MESSAGE),
        ):
            await self._resolve(_user(role=role, active=active))

        assert "Request refused: no access" in caplog.text
        assert "path=/api/v1/auth/me" in caplog.text

    async def test_missing_user_is_refused(self) -> None:
        with pytest.raises(AuthenticationError, match="User not found"):
            await self._resolve(None)
