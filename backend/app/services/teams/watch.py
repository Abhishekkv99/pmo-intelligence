"""Which PMO group chats are watched, and who in each is the consultant.

A chat is watched while it is tied to a placement (matched or chosen) that is
active and whose expected end date has not passed (UK date). Watching a chat
reads its members (``GET /chats/{id}/members``, ``Chat.ReadBasic.All``: names
and Entra ids, no messages) and finds the placement's consultant among them
by first and last name, as recording folders are matched; a single match
records the member's Entra id on the consultant when it has none. A chat whose
placement ended, or whose end date passed, stops being watched and keeps what
was stored.

The change-notification subscription that reads a watched chat's messages is
made by the subscription manager (Sprint 4 Phase 5), for every ``watching``
chat that has none; nothing here reads a message.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import LINKED, TeamsRepository
from app.models.enums import (
    FolderMatchStatus,
    PlacementStatus,
    TeamsWatchState,
)
from app.models.register import Consultant, Placement
from app.models.teams import TeamsGroup
from app.services.recordings.folder_names import fold
from app.services.recordings.name_match import ConsultantName, match_folder
from app.services.teams.graph_client import GraphClient, get_graph_client
from app.utils.exceptions import GraphError

logger = logging.getLogger(__name__)

# A consultant member a person chose, or one matched before, is kept.
MEMBER_DECIDED = frozenset(
    {FolderMatchStatus.MATCHED.value, FolderMatchStatus.CHOSEN.value}
)


class MemberSource(Protocol):
    async def list_members(self, graph_chat_id: str) -> list[dict[str, Any]]: ...


class GraphMemberSource:
    """A chat's members from Graph (names and Entra ids)."""

    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    async def list_members(self, graph_chat_id: str) -> list[dict[str, Any]]:
        return [m async for m in self.graph.get_all(f"/chats/{graph_chat_id}/members")]


@dataclass(frozen=True)
class MemberMatch:
    status: FolderMatchStatus
    oid: str | None = None


def is_watchable(chat: TeamsGroup, placement: Placement | None, now: datetime) -> bool:
    """Whether the chat should be watched as of ``now``."""
    if chat.match_status not in LINKED or placement is None:
        return False
    if placement.status != PlacementStatus.ACTIVE.value:
        return False
    today = now.astimezone(ZoneInfo(settings.health_timezone)).date()
    end = placement.expected_end_date
    return end is None or end >= today


def chat_members(listed: list[dict[str, Any]]) -> list[dict[str, str]]:
    """``[{"oid", "name"}]`` for the members that are people with an Entra id."""
    return [
        {"oid": str(m["userId"]), "name": str(m.get("displayName") or "")}
        for m in listed
        if m.get("userId")
    ]


def match_member(consultant: Consultant, members: list[dict[str, str]]) -> MemberMatch:
    """Find the consultant among a chat's members.

    The consultant's own Entra id wins when it is among them; otherwise a
    member is a candidate when their first or last name is a whole word of the
    consultant's name, and one member with both names wins among several.
    """
    if consultant.entra_oid and any(m["oid"] == consultant.entra_oid for m in members):
        return MemberMatch(FolderMatchStatus.MATCHED, consultant.entra_oid)
    by_id: dict[uuid.UUID, str] = {}
    people: list[ConsultantName] = []
    for member in members:
        try:
            key = uuid.UUID(member["oid"])
        except ValueError:
            continue
        by_id[key] = member["oid"]
        people.append(ConsultantName(key, member["name"]))
    found = match_folder(fold(consultant.full_name), people)
    if found.status == FolderMatchStatus.MATCHED and found.consultant_id is not None:
        return MemberMatch(FolderMatchStatus.MATCHED, by_id[found.consultant_id])
    return MemberMatch(found.status)


class TeamsWatch:
    def __init__(
        self, session: AsyncSession, members: MemberSource | None = None
    ) -> None:
        self.session = session
        self.members = members
        self.teams = TeamsRepository(session)

    async def review_placements(self, placement_ids: list[uuid.UUID]) -> None:
        """Review every chat of the placements (after a register edit)."""
        for chat_id in await self.teams.chat_ids_for_placements(placement_ids):
            await self.review(chat_id)

    async def review(self, chat_id: uuid.UUID) -> None:
        """Start or stop watching one chat, and read its members while watched."""
        row = await self.teams.chat_with_placement(chat_id)
        if row is None:
            return
        chat, placement, consultant = row
        now = datetime.now(UTC)

        if not is_watchable(chat, placement, now):
            if chat.watch_state in (
                TeamsWatchState.WATCHING.value,
                TeamsWatchState.FAILED.value,
            ):
                chat.watch_state = TeamsWatchState.STOPPED.value
                chat.stopped_at = now
                await self.session.commit()
                logger.info("Teams chat %s: no longer watched", chat.id)
            return

        if chat.watch_state != TeamsWatchState.WATCHING.value:
            chat.watched_at = now
            chat.stopped_at = None
        try:
            source = self.members or GraphMemberSource(get_graph_client())
            members = chat_members(await source.list_members(chat.graph_chat_id))
        except GraphError as exc:
            chat.watch_state = TeamsWatchState.FAILED.value
            chat.error_message = f"Members not read: {exc.message}"[:2000]
            await self.session.commit()
            logger.warning("Teams chat %s: members not read: %s", chat.id, exc.message)
            return

        chat.watch_state = TeamsWatchState.WATCHING.value
        chat.members = members
        chat.error_message = None
        if consultant is not None:
            await self._consultant_member(chat, consultant, members)
        await self.session.commit()
        logger.info(
            "Teams chat %s: watched, %d member(s), consultant member %s",
            chat.id,
            len(members),
            chat.consultant_member_match,
        )

    async def _consultant_member(
        self, chat: TeamsGroup, consultant: Consultant, members: list[dict[str, str]]
    ) -> None:
        if (
            chat.consultant_member_match in MEMBER_DECIDED
            and chat.consultant_member_oid
        ):
            return
        found = match_member(consultant, members)
        chat.consultant_member_match = found.status.value
        chat.consultant_member_oid = found.oid
        if found.oid is not None:
            await self.teams.link_consultant_oid(consultant, found.oid)
