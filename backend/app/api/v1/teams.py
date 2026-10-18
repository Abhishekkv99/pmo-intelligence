"""The PMO group chats: Admin > Teams.

For the global roles. Discovery finds the chats and ties most to their
placement; here a person sees every chat, asks for a discovery pass, links a
chat to its placement (or creates the placement from its title), and picks
the consultant among a chat's members when the name match could not.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import settings
from app.dependencies import DbSession, require_roles
from app.models.enums import Role, SnapshotReason
from app.rate_limiter import limiter
from app.schemas.recordings import ScanRequested
from app.schemas.register import QuickAddResult
from app.schemas.teams import (
    ChooseChatPlacement,
    ChooseConsultantMember,
    CreatePlacementFromTitle,
    TeamsChatList,
)
from app.services.health_jobs import request_recomputes
from app.services.teams.admin import TeamsAdmin
from app.services.teams.jobs import request_discovery, request_watch
from app.utils.exceptions import ConflictError

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


@router.get("/teams/chats", response_model=TeamsChatList, dependencies=ADMINS)
async def list_teams_chats(db: DbSession) -> TeamsChatList:
    """Every PMO group chat with its placement and watch state, and the last scan."""
    return await TeamsAdmin(db).list_chats()


@router.post(
    "/teams/scan",
    response_model=ScanRequested,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def scan_teams(request: Request) -> ScanRequested:
    """Queue a discovery pass now; ``queued`` is false when one is already waiting.

    409 while discovery is off (``TEAMS_DISCOVERY_ENABLED``).
    """
    if not settings.teams_discovery_enabled:
        raise ConflictError("Teams discovery is off on this environment")
    return ScanRequested(queued=request_discovery())


@router.put(
    "/teams/chats/{chat_id}/placement",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMINS,
)
async def choose_chat_placement(
    chat_id: uuid.UUID, body: ChooseChatPlacement, db: DbSession
) -> Response:
    """Tie the chat to a placement; discovery never changes it afterwards."""
    await TeamsAdmin(db).choose_placement(chat_id, body.placement_id)
    await db.commit()
    request_watch([chat_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/teams/chats/{chat_id}/placement",
    response_model=QuickAddResult,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def create_chat_placement(
    request: Request,
    chat_id: uuid.UUID,
    body: CreatePlacementFromTitle,
    db: DbSession,
) -> QuickAddResult:
    """Write the line through the quick add and tie the chat to its placement.

    Always 200, as the quick add is: ``applied`` says whether it wrote, and the
    line's errors say why not.
    """
    admin = TeamsAdmin(db)
    result, adder = await admin.create_placement_from_title(chat_id, body.line)
    if result.applied:
        await db.commit()
        request_recomputes(adder.changed_placement_ids, SnapshotReason.REGISTER)
        if admin.linked_placement_id is not None:
            request_watch([chat_id])
    return result


@router.put(
    "/teams/chats/{chat_id}/consultant-member",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMINS,
)
async def choose_consultant_member(
    chat_id: uuid.UUID, body: ChooseConsultantMember, db: DbSession
) -> Response:
    """Mark which member of the chat is the placement's consultant."""
    await TeamsAdmin(db).choose_consultant_member(chat_id, body.oid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
