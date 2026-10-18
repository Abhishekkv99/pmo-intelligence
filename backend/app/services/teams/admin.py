"""Admin > Teams: list the PMO group chats, and let a person settle the rest.

A chat discovery could not tie to one placement is linked by hand (``chosen``)
or gets its placement created from its title through the quick add, and is
then never re-matched. A chat whose consultant member is ambiguous gets one
chosen from its members. Each change is committed by the route, which then
queues the chat's watch review.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import (
    FolderMatchStatus,
    HistoryState,
    TeamsChatMatch,
    TeamsWatchState,
)
from app.models.teams import TeamsGroup
from app.schemas.register import QuickAddResult
from app.schemas.teams import (
    ParsedTitle,
    TeamsChatItem,
    TeamsChatList,
    TeamsMember,
    TeamsPlacement,
    TeamsScanSummary,
)
from app.services.register_quick_add import QuickAdd
from app.utils.exceptions import NotFoundError, ValidationError


def quick_add_line(chat: TeamsGroup) -> str:
    """The chat's title as a line the quick add reads, when the title was read."""
    if chat.parsed_start_date is None or chat.parsed_end_date is None:
        return chat.title
    start, end = chat.parsed_start_date, chat.parsed_end_date
    return (
        f"PRJ ITC {chat.parsed_stack} - {chat.parsed_consultant_name} - "
        f"{chat.parsed_client_name} - {start.day}/{start.month}/{start.year} - "
        f"{end.day}/{end.month}/{end.year}"
    )


class TeamsAdmin:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.teams = TeamsRepository(session)
        # The placement an applied "create from title" linked, for the route.
        self.linked_placement_id: uuid.UUID | None = None

    async def list_chats(self) -> TeamsChatList:
        chats = await self.teams.list_chats()
        wanted = {c.placement_id for c in chats if c.placement_id is not None}
        for chat in chats:
            wanted.update(uuid.UUID(i) for i in chat.candidate_placement_ids)
        placements = await self.teams.placement_summaries(list(wanted))
        scan = await self.teams.latest_scan()
        return TeamsChatList(
            chats=[self._item(chat, placements) for chat in chats],
            latest_scan=(
                TeamsScanSummary.model_validate(scan, from_attributes=True)
                if scan
                else None
            ),
            discovery_enabled=settings.teams_discovery_enabled,
            watching_enabled=settings.teams_enabled,
        )

    async def choose_placement(
        self, chat_id: uuid.UUID, placement_id: uuid.UUID
    ) -> None:
        chat = await self._chat(chat_id)
        if not await self.teams.placement_exists(placement_id):
            raise ValidationError(f"Placement {placement_id} does not exist")
        self._link(chat, placement_id)

    async def create_placement_from_title(
        self, chat_id: uuid.UUID, line: str
    ) -> tuple[QuickAddResult, QuickAdd]:
        """Write the line through the quick add and, when it applied, link the
        chat to the placement it found or created."""
        chat = await self._chat(chat_id)
        adder = QuickAdd(self.session)
        result = await adder.run([line], dry_run=False)
        placement_id = adder.placement_of_line.get(1)
        if result.applied and placement_id is not None:
            self._link(chat, placement_id)
            self.linked_placement_id = placement_id
        return result, adder

    async def choose_consultant_member(self, chat_id: uuid.UUID, oid: str) -> None:
        chat = await self._chat(chat_id)
        if not any(member.get("oid") == oid for member in chat.members):
            raise ValidationError("That person is not a member of the chat")
        chat.consultant_member_oid = oid
        chat.consultant_member_match = FolderMatchStatus.CHOSEN.value
        if chat.placement_id is not None:
            consultant = await self.teams.placement_consultant(chat.placement_id)
            if consultant is not None:
                await self.teams.link_consultant_oid(consultant, oid)

    async def _chat(self, chat_id: uuid.UUID) -> TeamsGroup:
        chat = await self.teams.get_chat(chat_id)
        if chat is None:
            raise NotFoundError("Teams chat", str(chat_id))
        return chat

    @staticmethod
    def _link(chat: TeamsGroup, placement_id: uuid.UUID) -> None:
        if chat.placement_id != placement_id:
            # Another placement may mean another consultant: find them again.
            chat.consultant_member_oid = None
            chat.consultant_member_match = FolderMatchStatus.UNMATCHED.value
        chat.placement_id = placement_id
        chat.match_status = TeamsChatMatch.CHOSEN.value
        chat.candidate_placement_ids = []
        chat.error_message = None

    @staticmethod
    def _item(
        chat: TeamsGroup, placements: dict[uuid.UUID, TeamsPlacement]
    ) -> TeamsChatItem:
        members = [
            TeamsMember(oid=m["oid"], name=m.get("name", "")) for m in chat.members
        ]
        consultant_member = next(
            (m for m in members if m.oid == chat.consultant_member_oid), None
        )
        parsed = (
            ParsedTitle(
                stack=chat.parsed_stack or "",
                consultant=chat.parsed_consultant_name or "",
                client=chat.parsed_client_name or "",
                start_date=chat.parsed_start_date,
                end_date=chat.parsed_end_date,
            )
            if chat.parsed_start_date is not None and chat.parsed_end_date is not None
            else None
        )
        return TeamsChatItem(
            id=chat.id,
            title=chat.title,
            parsed=parsed,
            quick_add_line=quick_add_line(chat),
            match_status=TeamsChatMatch(chat.match_status),
            placement=(
                placements.get(chat.placement_id) if chat.placement_id else None
            ),
            candidates=[
                placements[uuid.UUID(i)]
                for i in chat.candidate_placement_ids
                if uuid.UUID(i) in placements
            ],
            watch_state=TeamsWatchState(chat.watch_state),
            watched_at=chat.watched_at,
            stopped_at=chat.stopped_at,
            members=members,
            consultant_member=consultant_member,
            consultant_member_match=FolderMatchStatus(chat.consultant_member_match),
            last_message_at=chat.last_message_at,
            history_state=HistoryState(chat.history_state),
            error_message=chat.error_message,
        )
