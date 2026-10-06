"""Startup grant of the ``pmo_manager`` role to the configured admin emails.

The operator has no SQL access to the database, so the first PMO manager has
to come from configuration: ``BOOTSTRAP_ADMIN_EMAILS`` names them, and this sweep
runs in the application lifespan so a new deployment elevates every listed
user that already has a row. A listed user with no row yet is elevated the
moment the row is created (SSO JIT provisioning, local ``register``) — see
``app.utils.entitlements.elevate_if_bootstrap_admin``, which owns the rule.

Elevate-only: the sweep never demotes, so editing the list cannot lock an
admin out, and it is idempotent, so restarting the container is free.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.db.session import async_session_factory
from app.utils.entitlements import bootstrap_admin_emails, elevate_if_bootstrap_admin

logger = logging.getLogger(__name__)


async def _elevate(session: AsyncSession, emails: frozenset[str]) -> int:
    users = await UserRepository(session).get_by_emails(emails)
    changed = sum(1 for user in users if elevate_if_bootstrap_admin(user))
    if changed:
        await session.flush()
    missing = emails - {user.email.lower() for user in users}
    for email in sorted(missing):
        # Not an error: the row is elevated when that person first signs in.
        logger.info("Bootstrap admin has no user row yet: email=%s", email)
    return changed


async def elevate_bootstrap_admins(session: AsyncSession | None = None) -> int:
    """Elevate every configured admin that has a user row. Returns the count changed.

    With an empty list this returns 0 without touching the database. If
    ``session`` is provided it is used as-is and the caller commits; otherwise
    a fresh session is opened and committed. The startup path calls it with
    no arguments.
    """
    emails = bootstrap_admin_emails()
    if not emails:
        return 0
    if session is not None:
        return await _elevate(session, emails)
    async with async_session_factory() as owned_session:
        changed = await _elevate(owned_session, emails)
        await owned_session.commit()
        return changed
