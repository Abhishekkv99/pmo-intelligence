"""The watch review against a real database and a fake member list.

Pins what the plan promises: a chat tied to an active placement is watched
and its members read, the consultant member is found by name and their Entra
id recorded once, a person's choice is kept, a failure is recorded, a chat
whose placement ended stops being watched and keeps what it had, and a chat
not tied to a placement is never read.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import FolderMatchStatus, PlacementStatus, TeamsChatMatch
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup
from app.services.teams.watch import TeamsWatch
from app.utils.exceptions import GraphError

ALEX_OID = "8f0c5a2e-1111-4a6b-9a35-000000000001"
PMO_OID = "8f0c5a2e-3333-4a6b-9a35-000000000003"
MEMBERS = [
    {"userId": ALEX_OID, "displayName": "Alex Sample"},
    {"userId": PMO_OID, "displayName": "Pat Manager"},
]


class FakeMembers:
    def __init__(self, members: list[dict[str, Any]] | None = None) -> None:
        self.members = MEMBERS if members is None else members
        self.asked: list[str] = []
        self.fail: GraphError | None = None

    async def list_members(self, graph_chat_id: str) -> list[dict[str, Any]]:
        self.asked.append(graph_chat_id)
        if self.fail:
            raise self.fail
        return self.members


async def _placement(
    db: AsyncSession,
    name: str = "Alex Sample",
    end: date | None = None,
    status: PlacementStatus = PlacementStatus.ACTIVE,
) -> Placement:
    consultant = Consultant(full_name=name)
    firm = Client(
        name=f"Client of {name}", normalized_name=f"client of {name}".casefold()
    )
    db.add_all([consultant, firm])
    await db.flush()
    project = Project(client_id=firm.id, name="Payments")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date(2026, 9, 1),
        expected_end_date=end,
        status=status.value,
    )
    db.add(placement)
    await db.flush()
    return placement


async def _chat(
    db: AsyncSession,
    placement: Placement | None,
    match: TeamsChatMatch = TeamsChatMatch.MATCHED,
    graph_id: str = "19:alex@thread.v2",
) -> TeamsGroup:
    chat = TeamsGroup(
        graph_chat_id=graph_id,
        title="PRJ ITC DS - Alex Sample - Demo - 1/9/2026 - 31/3/2027",
        match_status=match.value,
        placement_id=placement.id if placement else None,
    )
    db.add(chat)
    await db.flush()
    return chat


async def _fresh(db: AsyncSession, row: Any) -> Any:
    await db.refresh(row)
    return row


class TestWatching:
    async def test_a_linked_chat_is_watched_and_its_consultant_found(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session, end=date.today() + timedelta(days=90))
        chat = await _chat(db_session, placement)
        members = FakeMembers()

        await TeamsWatch(db_session, members).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert members.asked == ["19:alex@thread.v2"]
        assert chat.watch_state == "watching"
        assert chat.watched_at is not None and chat.stopped_at is None
        assert chat.members == [
            {"oid": ALEX_OID, "name": "Alex Sample"},
            {"oid": PMO_OID, "name": "Pat Manager"},
        ]
        assert chat.consultant_member_match == FolderMatchStatus.MATCHED.value
        assert chat.consultant_member_oid == ALEX_OID
        consultant = await db_session.get(Consultant, placement.consultant_id)
        assert consultant is not None
        await db_session.refresh(consultant)
        assert consultant.entra_oid == ALEX_OID

    async def test_a_second_review_keeps_the_first_watched_time(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session, await _placement(db_session))
        await TeamsWatch(db_session, FakeMembers()).review(chat.id)
        first = (await _fresh(db_session, chat)).watched_at

        await TeamsWatch(db_session, FakeMembers()).review(chat.id)

        assert (await _fresh(db_session, chat)).watched_at == first

    async def test_an_entra_id_another_consultant_holds_is_not_recorded(
        self, db_session: AsyncSession
    ) -> None:
        holder = Consultant(full_name="Someone Else", entra_oid=ALEX_OID)
        db_session.add(holder)
        placement = await _placement(db_session)
        chat = await _chat(db_session, placement)

        await TeamsWatch(db_session, FakeMembers()).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert chat.consultant_member_oid == ALEX_OID
        consultant = await db_session.get(Consultant, placement.consultant_id)
        assert consultant is not None and consultant.entra_oid is None

    async def test_an_ambiguous_member_waits_for_a_person(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _chat(db_session, await _placement(db_session))
        members = FakeMembers(
            [
                {"userId": ALEX_OID, "displayName": "Alex Other"},
                {"userId": PMO_OID, "displayName": "Alex Third"},
            ]
        )

        await TeamsWatch(db_session, members).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert chat.watch_state == "watching"
        assert chat.consultant_member_match == FolderMatchStatus.NEEDS_CHOICE.value
        assert chat.consultant_member_oid is None

    async def test_a_chosen_member_is_kept(self, db_session: AsyncSession) -> None:
        chat = await _chat(db_session, await _placement(db_session))
        chat.consultant_member_match = FolderMatchStatus.CHOSEN.value
        chat.consultant_member_oid = PMO_OID
        await db_session.flush()

        await TeamsWatch(db_session, FakeMembers()).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert chat.consultant_member_match == FolderMatchStatus.CHOSEN.value
        assert chat.consultant_member_oid == PMO_OID

    async def test_a_failed_read_is_recorded(self, db_session: AsyncSession) -> None:
        chat = await _chat(db_session, await _placement(db_session))
        members = FakeMembers()
        members.fail = GraphError("Graph GET /chats/x/members answered 403: Forbidden")

        await TeamsWatch(db_session, members).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert chat.watch_state == "failed"
        assert chat.error_message == (
            "Members not read: Graph GET /chats/x/members answered 403: Forbidden"
        )


class TestNotWatching:
    @pytest.mark.parametrize(
        "match",
        [
            TeamsChatMatch.UNMATCHED,
            TeamsChatMatch.NEEDS_CHOICE,
            TeamsChatMatch.UNPARSED,
        ],
    )
    async def test_a_chat_not_tied_to_a_placement_is_never_read(
        self, db_session: AsyncSession, match: TeamsChatMatch
    ) -> None:
        chat = await _chat(db_session, None, match=match)
        members = FakeMembers()

        await TeamsWatch(db_session, members).review(chat.id)

        assert members.asked == []
        assert (await _fresh(db_session, chat)).watch_state == "not_watched"

    async def test_a_chat_whose_placement_ended_stops_and_keeps_its_members(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        chat = await _chat(db_session, placement)
        await TeamsWatch(db_session, FakeMembers()).review(chat.id)
        placement.status = PlacementStatus.ENDED.value
        await db_session.flush()
        members = FakeMembers()

        await TeamsWatch(db_session, members).review(chat.id)

        chat = await _fresh(db_session, chat)
        assert members.asked == []
        assert chat.watch_state == "stopped"
        assert chat.stopped_at is not None
        assert len(chat.members) == 2

    async def test_a_chat_whose_end_date_passed_is_not_watched(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session, end=date.today() - timedelta(days=2))
        chat = await _chat(db_session, placement)
        members = FakeMembers()

        await TeamsWatch(db_session, members).review(chat.id)

        assert members.asked == []
        assert (await _fresh(db_session, chat)).watch_state == "not_watched"


class TestReviewPlacements:
    async def test_reviews_every_chat_of_the_placement(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        first = await _chat(db_session, placement)
        second = await _chat(db_session, placement, graph_id="19:second@thread.v2")
        other = await _chat(
            db_session, await _placement(db_session, "Sam Other"), graph_id="19:o@t"
        )
        members = FakeMembers()

        await TeamsWatch(db_session, members).review_placements([placement.id])

        assert sorted(members.asked) == ["19:alex@thread.v2", "19:second@thread.v2"]
        for chat in (first, second):
            assert (await _fresh(db_session, chat)).watch_state == "watching"
        assert (await _fresh(db_session, other)).watch_state == "not_watched"

    async def test_linked_chat_ids_lists_tied_and_watched_chats(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        tied = await _chat(db_session, placement)
        loose = await _chat(
            db_session, None, match=TeamsChatMatch.UNMATCHED, graph_id="19:l@t"
        )

        ids = await TeamsRepository(db_session).linked_chat_ids()

        assert tied.id in ids and loose.id not in ids
        assert set(ids) <= set(
            (await db_session.execute(select(TeamsGroup.id))).scalars()
        )
