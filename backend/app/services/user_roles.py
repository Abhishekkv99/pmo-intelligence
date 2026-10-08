"""Granting and removing roles, until the Admin "Users and roles" page exists.

A role is what lets a person sign in at all (``app.utils.entitlements``), so
granting one to an address that has never signed in creates the user by email.
The first SSO sign-in finds that row by email and links the Entra account to
it (``SSOService.find_user_for_sign_in``). Removing a role ends every session
the user holds.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.models.enums import Role
from app.services.auth_service import AuthService
from app.utils.entitlements import is_bootstrap_admin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserSummary:
    """One line of the user list; no tokens, no Entra ids."""

    email: str
    full_name: str
    role: str | None
    is_active: bool
    signed_in_with_microsoft: bool


class UserRoleService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def set_role(self, email: str, role: Role | None) -> str:
        """Give ``email`` the ``role``, or remove its role when ``role`` is None.

        Returns a one-line description of what changed, for the task log.
        """
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError(f"not an email address: {email!r}")
        new_role = role.value if role is not None else None
        user = await self.user_repo.get_by_email(email)

        if user is None:
            if new_role is None:
                return f"{email}: no such user, nothing to remove"
            await self.user_repo.create(
                email=email,
                hashed_password=None,
                full_name=email.split("@")[0],
                auth_provider="microsoft_entra",
                role=new_role,
            )
            logger.info("Role granted to a new user: email=%s role=%s", email, new_role)
            return (
                f"{email}: created with role {new_role}; "
                "linked to Microsoft at first sign-in"
            )

        old_role = user.role
        if old_role == new_role:
            return f"{email}: already {new_role or 'without a role'}, nothing changed"
        user.role = new_role
        await self.session.flush()
        logger.info(
            "Role changed: email=%s user_id=%s role=%s->%s",
            email,
            user.id,
            old_role,
            new_role,
        )
        if new_role is not None:
            return f"{email}: role {old_role or 'none'} -> {new_role}"

        revoked = await AuthService(self.session).revoke_all_user_tokens(user.id)
        message = (
            f"{email}: role {old_role} removed; {revoked} session(s) ended, "
            "and any open page stops working within 15 minutes"
        )
        if is_bootstrap_admin(email):
            message += (
                ". Warning: this address is in BOOTSTRAP_ADMIN_EMAILS, so it becomes "
                "pmo_manager again at its next sign-in or deploy; remove it there too"
            )
        return message

    async def list_users(self) -> list[UserSummary]:
        return [
            UserSummary(
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                signed_in_with_microsoft=user.entra_oid is not None,
            )
            for user in await self.user_repo.list_by_email()
        ]
