"""Integration tests for the bootstrap-admin sweep against a real database."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.user_repo import UserRepository
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.bootstrap_admins import elevate_bootstrap_admins


async def _seed(db_session: AsyncSession, email: str, role: str | None) -> User:
    return await UserRepository(db_session).create(
        email=email,
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=email.split("@")[0],
        role=role,
    )


class TestElevateBootstrapAdmins:
    """The sweep elevates exactly the listed rows, matches case-insensitively,
    never demotes, and is idempotent."""

    async def test_elevates_only_listed_users_and_is_idempotent(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        listed = await _seed(db_session, "Admin@Example.com", None)
        unlisted = await _seed(db_session, "user@example.com", None)
        already = await _seed(db_session, "other@example.com", "pmo_manager")
        monkeypatch.setattr(
            settings, "bootstrap_admin_emails", "admin@example.com, nobody@example.com"
        )

        assert await elevate_bootstrap_admins(db_session) == 1

        for user in (listed, unlisted, already):
            await db_session.refresh(user)
        assert listed.role == "pmo_manager"
        assert unlisted.role is None
        assert already.role == "pmo_manager"

        # A second pass finds nothing left to do.
        assert await elevate_bootstrap_admins(db_session) == 0

    async def test_empty_list_changes_nothing(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await _seed(db_session, "admin@example.com", None)
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "")

        assert await elevate_bootstrap_admins(db_session) == 0

        await db_session.refresh(user)
        assert user.role is None

    async def test_raises_a_scoped_role_but_leaves_a_global_one(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sme = await _seed(db_session, "sme@example.com", "sme")
        admin = await _seed(db_session, "ops@example.com", "admin")
        monkeypatch.setattr(
            settings, "bootstrap_admin_emails", "sme@example.com, ops@example.com"
        )

        assert await elevate_bootstrap_admins(db_session) == 1

        await db_session.refresh(sme)
        await db_session.refresh(admin)
        assert sme.role == "pmo_manager"
        assert admin.role == "admin"
