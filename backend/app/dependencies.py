import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.access_log_repo import AccessLogRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import async_session_factory
from app.models.enums import Role
from app.models.register import Placement, Project
from app.models.session import Session
from app.models.user import User
from app.services.auth_service import SESSION_ENDED_MESSAGE, AuthService
from app.services.media_token import check_media_token
from app.utils.entitlements import (
    PlacementPeople,
    assert_can_read_placement,
    assert_has_role,
    may_use_app,
)
from app.utils.exceptions import AuthenticationError, NotFoundError

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Marks a dependency as an entitlement guard. The route-coverage test
# (tests/unit/test_entitlement_coverage.py) looks for it on every /api/v1
# route, so a route cannot ship without one by accident.
GUARD_ATTR = "__entitlement_guard__"


def _guard[F: Callable[..., Any]](func: F) -> F:
    setattr(func, GUARD_ATTR, True)
    return func


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# The request's session. scope="function" commits before the response is sent:
# FastAPI's default for a yield dependency ends it after the response, so a 201
# could reach the browser before its row was committed (a list read straight
# after a save then missed it), and a failed commit still answered success.
# Every route and guard takes the session through this alias.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]


async def get_current_user(
    request: Request,
    db: DbSession,
    token: str = Depends(oauth2_scheme),
) -> User:
    """Validate JWT token and return the current user."""
    user_id: uuid.UUID = AuthService.decode_access_token(token)
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise AuthenticationError("User not found")
    if not may_use_app(user):
        # Disabled, or the role was removed since the access token was issued
        logger.warning(
            "Request refused: no access (user_id=%s role=%s active=%s path=%s)",
            user.id,
            user.role,
            user.is_active,
            request.url.path,
        )
        raise AuthenticationError(SESSION_ENDED_MESSAGE)
    return user


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """A dependency that answers 403 unless the caller holds one of ``roles``.

    For operations that address no placement: admin pages, the queue
    status. Use as ``dependencies=[Depends(require_roles(Role.ADMIN))]``.
    """

    @_guard
    async def dependency(
        request: Request, current_user: User = Depends(get_current_user)
    ) -> User:
        assert_has_role(current_user, roles, request.url.path)
        return current_user

    return dependency


# --- By-id placement scope ----------------------------------------------------
#
# Applied to every route addressed by a placement id (and, through the
# placement, to its sessions, flags and actions). A placement outside the
# caller's scope raises a NotFoundError built exactly as a missing row's, so
# ids cannot be enumerated. These are dependencies rather than service-layer
# checks because the same services also run from the processing queue and
# schedulers with no user at all.


async def _load_scoped_placement(
    placement_id: uuid.UUID, db: AsyncSession, current_user: User
) -> Placement:
    # Explicit join for the tech lead: a lazy relationship would raise
    # MissingGreenlet under async.
    stmt = (
        select(Placement, Project.tech_lead_user_id)
        .join(Project, Project.id == Placement.project_id)
        .where(Placement.id == placement_id)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise NotFoundError("Placement", str(placement_id))
    placement: Placement = row[0]
    tech_lead_user_id: uuid.UUID | None = row[1]
    people = PlacementPeople(
        ps_user_id=placement.ps_user_id,
        sme_user_id=placement.sme_user_id,
        tech_lead_user_id=tech_lead_user_id,
    )
    assert_can_read_placement(current_user, people, placement_id)
    return placement


@_guard
async def require_placement_scope(
    placement_id: uuid.UUID,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> Placement:
    """404 unless the placement exists and the caller may read it."""
    return await _load_scoped_placement(placement_id, db, current_user)


@_guard
async def require_logged_placement_scope(
    request: Request,
    placement_id: uuid.UUID,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> Placement:
    """``require_placement_scope`` plus an ``access_log`` row for the read.

    For the routes that show a consultant's data (the consultant page and
    its parts), so the PMO manager can see who looked at whom.
    """
    placement = await _load_scoped_placement(placement_id, db, current_user)
    await AccessLogRepository(db).record(
        current_user.id, placement.id, request.url.path
    )
    return placement


PlacementScope = Annotated[Placement, Depends(require_placement_scope)]
LoggedPlacementScope = Annotated[Placement, Depends(require_logged_placement_scope)]


# --- By-id session scope ------------------------------------------------------
#
# A session is read through its placement: the same rule, the same 404.


async def _load_scoped_session(
    session_id: uuid.UUID, db: AsyncSession, current_user: User
) -> Session:
    stmt = (
        select(
            Session,
            Placement.ps_user_id,
            Placement.sme_user_id,
            Project.tech_lead_user_id,
        )
        .join(Placement, Placement.id == Session.placement_id)
        .join(Project, Project.id == Placement.project_id)
        .where(Session.id == session_id)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise NotFoundError("Session", str(session_id))
    session: Session = row[0]
    people = PlacementPeople(
        ps_user_id=row[1], sme_user_id=row[2], tech_lead_user_id=row[3]
    )
    assert_can_read_placement(current_user, people, session_id, resource="Session")
    return session


@_guard
async def require_session_scope(
    session_id: uuid.UUID,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> Session:
    """404 unless the session exists and the caller may read its placement."""
    return await _load_scoped_session(session_id, db, current_user)


@_guard
async def require_logged_session_scope(
    request: Request,
    session_id: uuid.UUID,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> Session:
    """``require_session_scope`` plus an ``access_log`` row for its placement."""
    session = await _load_scoped_session(session_id, db, current_user)
    await AccessLogRepository(db).record(
        current_user.id, session.placement_id, request.url.path
    )
    return session


SessionScope = Annotated[Session, Depends(require_session_scope)]
LoggedSessionScope = Annotated[Session, Depends(require_logged_session_scope)]


# --- Token scope ----------------------------------------------------------------
#
# A route the browser reaches without the Bearer token (an <audio> source)
# carries a token naming the one row it may read. The coverage test requires
# such a route to carry a guard marked with TOKEN_GUARD_ATTR.

TOKEN_GUARD_ATTR = "__token_guard__"


def _token_guard[F: Callable[..., Any]](func: F) -> F:
    setattr(func, TOKEN_GUARD_ATTR, True)
    return _guard(func)


@_token_guard
async def require_media_token(session_id: uuid.UUID, token: str) -> uuid.UUID:
    """404 unless ``token`` is a live media token for ``session_id``."""
    check_media_token(token, session_id)
    return session_id
