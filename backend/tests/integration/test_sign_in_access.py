"""Integration tests: only an active user with a role keeps a session, and a
role granted by email is picked up by the first SSO sign-in."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import Role
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.sso_service import SSOService
from app.services.user_roles import UserRoleService
from app.utils.exceptions import AuthenticationError


async def _users_with_email(db_session: AsyncSession, email: str) -> int:
    count = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == email)
    )
    return int(count or 0)


async def _live_tokens(db_session: AsyncSession, user: User) -> int:
    count = await db_session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.is_revoked.is_(False))
    )
    return int(count or 0)


class TestRoleGrantAndFirstSignIn:
    async def test_granted_role_is_linked_at_first_sign_in(
        self, db_session: AsyncSession
    ) -> None:
        message = await UserRoleService(db_session).set_role(
            " Jane.Doe@Example.com ", Role.SME
        )
        assert "created with role sme" in message

        user = await SSOService(db_session).find_user_for_sign_in(
            {"oid": "oid-jane", "email": "jane.doe@example.com", "name": "Jane Doe"}
        )

        assert user is not None
        assert user.email == "jane.doe@example.com"
        assert user.entra_oid == "oid-jane"
        assert user.full_name == "Jane Doe"
        assert user.role == "sme"
        assert await _users_with_email(db_session, "jane.doe@example.com") == 1

    async def test_unknown_account_leaves_no_row(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "")

        user = await SSOService(db_session).find_user_for_sign_in(
            {"oid": "oid-stranger", "email": "stranger@example.com"}
        )

        assert user is None
        assert await _users_with_email(db_session, "stranger@example.com") == 0

    async def test_changing_and_listing_roles(self, db_session: AsyncSession) -> None:
        service = UserRoleService(db_session)
        await service.set_role("lead@example.com", Role.TECH_LEAD)

        assert "tech_lead -> ps" in await service.set_role("lead@example.com", Role.PS)
        assert "nothing changed" in await service.set_role("lead@example.com", Role.PS)
        listed = {u.email: u for u in await service.list_users()}
        assert listed["lead@example.com"].role == "ps"
        assert listed["lead@example.com"].signed_in_with_microsoft is False

    async def test_removing_a_role_that_was_never_granted_creates_nothing(
        self, db_session: AsyncSession
    ) -> None:
        message = await UserRoleService(db_session).set_role("ghost@example.com", None)

        assert "no such user" in message
        assert await _users_with_email(db_session, "ghost@example.com") == 0

    async def test_not_an_email_address_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(ValueError, match="not an email address"):
            await UserRoleService(db_session).set_role("jane", Role.SME)


class TestRemovingARoleEndsTheSession:
    async def test_removal_revokes_every_refresh_token(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        auth = AuthService(db_session)
        raw = AuthService.create_refresh_token()
        await auth.store_refresh_token(test_user.id, raw)
        await auth.store_refresh_token(test_user.id, AuthService.create_refresh_token())

        message = await UserRoleService(db_session).set_role(test_user.email, None)

        assert "2 session(s) ended" in message
        assert await _live_tokens(db_session, test_user) == 0
        with pytest.raises(AuthenticationError):
            await auth.validate_and_rotate_refresh_token(raw)

    async def test_refresh_is_refused_once_the_role_is_gone(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """A role cleared without the CLI (e.g. by hand) still ends sessions."""
        auth = AuthService(db_session)
        raw = AuthService.create_refresh_token()
        await auth.store_refresh_token(test_user.id, raw)
        await auth.store_refresh_token(test_user.id, AuthService.create_refresh_token())
        test_user.role = None
        await db_session.flush()

        with pytest.raises(AuthenticationError, match="session has ended"):
            await auth.validate_and_rotate_refresh_token(raw)

        assert await _live_tokens(db_session, test_user) == 0

    async def test_refresh_works_while_the_role_is_held(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        auth = AuthService(db_session)
        raw = AuthService.create_refresh_token()
        await auth.store_refresh_token(test_user.id, raw)

        assert await auth.validate_and_rotate_refresh_token(raw) == test_user.id
