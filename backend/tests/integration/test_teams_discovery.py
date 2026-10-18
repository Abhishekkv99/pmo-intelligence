"""Teams discovery against a real database and a fake chat source.

Pins what the plan promises: only group chats titled PRJ ITC are kept, the
accounts' lists are merged by chat id, each chat is tied to its placement
from the title, unread and unresolved chats are tried again as the register
grows, a person's choice is never overwritten, nothing but titles is read,
and every pass leaves a ``teams_scans`` row saying how it ended. Titles are
synthetic, in the surveyed shapes.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import ScanStatus, TeamsChatMatch
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup, TeamsScan
from app.services.teams.discovery import TeamsDiscovery

ANA = "ana@example.com"
BEN = "ben@example.com"

ALEX_TITLE = "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/3/2027"
PRIYA_TITLE = "PRJ ITC-BD-Priya-Northwind-1/9/26-31/3/27"
ODD_TITLE = "PRJ ITC - team social"


def _chat(chat_id: str, topic: str | None, chat_type: str = "group") -> dict[str, Any]:
    return {"id": chat_id, "topic": topic, "chatType": chat_type}


class FakeChats:
    def __init__(self, lists: dict[str, list[dict[str, Any]]]) -> None:
        self.lists = lists
        self.asked: list[str] = []
        self.fail: Exception | None = None

    async def list_chats(self, account: str) -> list[dict[str, Any]]:
        self.asked.append(account)
        if self.fail:
            raise self.fail
        return self.lists.get(account, [])


@pytest.fixture(autouse=True)
def _accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "teams_discovery_accounts", [ANA, BEN])


@pytest.fixture
def source() -> FakeChats:
    return FakeChats(
        {
            ANA: [
                _chat("19:alex@thread.v2", ALEX_TITLE),
                _chat("19:priya@thread.v2", PRIYA_TITLE),
                _chat("19:lunch@thread.v2", "Team lunch"),
                _chat("19:one@thread.v2", None, chat_type="oneOnOne"),
            ],
            BEN: [
                _chat("19:alex@thread.v2", ALEX_TITLE),
                _chat("19:odd@thread.v2", ODD_TITLE),
                _chat("19:meeting@thread.v2", ALEX_TITLE, chat_type="meeting"),
            ],
        }
    )


async def _placement(
    db: AsyncSession, consultant: str, client: str, start: date
) -> Placement:
    person = Consultant(full_name=consultant)
    firm = await db.scalar(select(Client).where(Client.name == client))
    if firm is None:
        firm = Client(name=client, normalized_name=client.casefold())
        db.add(firm)
    db.add(person)
    await db.flush()
    project = Project(client_id=firm.id, name=f"Project {consultant}")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=person.id, project_id=project.id, start_date=start
    )
    db.add(placement)
    await db.flush()
    return placement


async def _chat_row(db: AsyncSession, chat_id: str) -> TeamsGroup:
    chat = await db.scalar(
        select(TeamsGroup).where(TeamsGroup.graph_chat_id == chat_id)
    )
    assert chat is not None
    await db.refresh(chat)
    return chat


async def _count(db: AsyncSession, model: type) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


class TestFirstPass:
    async def test_keeps_pmo_group_chats_once_and_ties_them_to_placements(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        alex = await _placement(
            db_session, "Alex Sample", "Demo Client", date(2026, 9, 21)
        )

        scan = await TeamsDiscovery(db_session, source).run()

        assert source.asked == [ANA, BEN]
        assert (scan.status, scan.chats_seen, scan.chats_added, scan.chats_matched) == (
            ScanStatus.COMPLETED.value,
            3,
            3,
            1,
        )
        assert await _count(db_session, TeamsGroup) == 3

        matched = await _chat_row(db_session, "19:alex@thread.v2")
        assert matched.match_status == TeamsChatMatch.MATCHED.value
        assert matched.placement_id == alex.id
        assert (matched.parsed_stack, matched.parsed_consultant_name) == (
            "DS",
            "Alex Sample",
        )
        assert matched.parsed_start_date == date(2026, 9, 21)
        assert matched.error_message is None

        priya = await _chat_row(db_session, "19:priya@thread.v2")
        assert priya.match_status == TeamsChatMatch.UNMATCHED.value
        assert priya.parsed_client_name == "Northwind"
        assert priya.parsed_end_date == date(2027, 3, 31)

        odd = await _chat_row(db_session, "19:odd@thread.v2")
        assert odd.match_status == TeamsChatMatch.UNPARSED.value
        assert odd.parsed_consultant_name is None
        assert odd.error_message is not None
        assert odd.error_message.startswith("Title not read: ")

    async def test_new_chats_are_not_watched(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        await TeamsDiscovery(db_session, source).run()

        chat = await _chat_row(db_session, "19:alex@thread.v2")
        assert chat.watch_state == "not_watched"
        assert chat.history_state == "none"
        assert chat.members == []


class TestLaterPasses:
    async def test_an_unmatched_chat_matches_once_its_placement_is_registered(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        await TeamsDiscovery(db_session, source).run()
        priya = await _placement(
            db_session, "Priya Shah", "Northwind", date(2026, 9, 1)
        )

        scan = await TeamsDiscovery(db_session, source).run()

        chat = await _chat_row(db_session, "19:priya@thread.v2")
        assert chat.match_status == TeamsChatMatch.MATCHED.value
        assert chat.placement_id == priya.id
        assert (scan.chats_added, scan.chats_matched) == (0, 1)

    async def test_a_renamed_chat_is_read_again(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        await TeamsDiscovery(db_session, source).run()
        await _placement(db_session, "Sam Other", "Demo Client", date(2026, 10, 5))
        source.lists[BEN][1] = _chat(
            "19:odd@thread.v2",
            "PRJ ITC QA - Sam Other - Demo Client - 5/10/26 - 5/4/27",
        )

        await TeamsDiscovery(db_session, source).run()

        chat = await _chat_row(db_session, "19:odd@thread.v2")
        assert chat.title.startswith("PRJ ITC QA - Sam Other")
        assert chat.match_status == TeamsChatMatch.MATCHED.value
        assert chat.error_message is None

    async def test_chosen_and_matched_chats_are_never_rematched(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        alex = await _placement(
            db_session, "Alex Sample", "Demo Client", date(2026, 9, 21)
        )
        other = await _placement(
            db_session, "Priya Patel", "Northwind", date(2026, 9, 1)
        )
        await TeamsDiscovery(db_session, source).run()
        priya = await _chat_row(db_session, "19:priya@thread.v2")
        priya.match_status = TeamsChatMatch.CHOSEN.value
        priya.placement_id = other.id
        await db_session.flush()

        # A second Alex at the same client and start would make it a choice.
        await _placement(db_session, "Alex Other", "Demo Client", date(2026, 9, 21))
        await _placement(db_session, "Priya Shah", "Northwind", date(2026, 9, 1))
        await TeamsDiscovery(db_session, source).run()

        alex_chat = await _chat_row(db_session, "19:alex@thread.v2")
        assert alex_chat.match_status == TeamsChatMatch.MATCHED.value
        assert alex_chat.placement_id == alex.id
        priya = await _chat_row(db_session, "19:priya@thread.v2")
        assert priya.match_status == TeamsChatMatch.CHOSEN.value
        assert priya.placement_id == other.id


class TestFailedPasses:
    async def test_failure_is_recorded_and_the_chats_are_unchanged(
        self, db_session: AsyncSession, source: FakeChats
    ) -> None:
        source.fail = PermissionError("Forbidden on /users/ana@example.com/chats")

        scan = await TeamsDiscovery(db_session, source).run()

        assert scan.status == ScanStatus.FAILED.value
        assert scan.error_message == (
            "PermissionError: Forbidden on /users/ana@example.com/chats"
        )
        assert scan.finished_at is not None
        assert await _count(db_session, TeamsGroup) == 0

    async def test_no_account_configured_is_a_failed_pass(
        self,
        db_session: AsyncSession,
        source: FakeChats,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "teams_discovery_accounts", [])

        scan = await TeamsDiscovery(db_session, source).run()

        assert scan.status == ScanStatus.FAILED.value
        assert "TEAMS_DISCOVERY_ACCOUNTS" in (scan.error_message or "")
        assert source.asked == []

    async def test_graph_not_configured_is_a_failed_pass(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "graph_tenant_id", "")

        scan = await TeamsDiscovery(db_session).run()

        assert scan.status == ScanStatus.FAILED.value
        assert "GRAPH_TENANT_ID" in (scan.error_message or "")

    async def test_takeover_sweep_fails_passes_left_running(
        self, db_session: AsyncSession
    ) -> None:
        repo = TeamsRepository(db_session)
        left = await repo.start_scan(datetime(2026, 10, 18, 9, 0, tzinfo=UTC))

        count = await repo.fail_running_scans(
            datetime(2026, 10, 18, 9, 5, tzinfo=UTC), "Interrupted"
        )

        assert count == 1
        await db_session.refresh(left)
        assert left.status == ScanStatus.FAILED.value
        assert left.error_message == "Interrupted"
        latest = await repo.latest_scan()
        assert latest is not None and latest.id == left.id
        assert await _count(db_session, TeamsScan) == 1
