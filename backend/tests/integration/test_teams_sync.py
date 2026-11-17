"""The sync of a watched chat against a real database and a fake message source.

Pins what the plan promises: the first sync stores the whole history (every
page) marked as history; later syncs read only what changed after the newest
stored change, less the overlap; new, edited and deleted messages and system
events are stored as such; a message read twice is stored once; authors get
their role from the chat; a chat not watched is never read; and a failed read
stores nothing. Names and text are made up.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.teams_repo import TeamsRepository
from app.models.enums import (
    HistoryState,
    PlacementStatus,
    Role,
    TeamsChatMatch,
    TeamsWatchState,
)
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import Message, TeamsGroup
from app.models.user import User
from app.services.teams.messages import WATERMARK_OVERLAP, TeamsSync
from app.utils.exceptions import GraphError

ALEX_OID = "8f0c5a2e-1111-4a6b-9a35-000000000001"
PS_OID = "8f0c5a2e-2222-4a6b-9a35-000000000002"
PMO_OID = "8f0c5a2e-3333-4a6b-9a35-000000000003"
GUEST_OID = "8f0c5a2e-4444-4a6b-9a35-000000000004"
T0 = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _msg(
    graph_id: str,
    minutes: int,
    text: str = "update",
    author: str | None = ALEX_OID,
    modified: int | None = None,
    deleted: int | None = None,
    kind: str = "message",
) -> dict[str, Any]:
    at = (T0 + timedelta(minutes=minutes)).isoformat()
    changed = T0 + timedelta(minutes=modified if modified is not None else minutes)
    return {
        "id": graph_id,
        "messageType": kind,
        "createdDateTime": at,
        "lastModifiedDateTime": changed.isoformat(),
        "deletedDateTime": (
            (T0 + timedelta(minutes=deleted)).isoformat() if deleted else None
        ),
        "from": {"user": {"id": author, "displayName": "Someone"}} if author else None,
        "body": {"contentType": "html", "content": f"<p>{text}</p>"},
    }


class FakeMessages:
    def __init__(self) -> None:
        self.history_items: list[dict[str, Any]] = []
        self.changes: list[dict[str, Any]] = []
        self.asked: list[tuple[str, str, datetime | None]] = []
        self.fail_after: int | None = None

    async def _yield(
        self, items: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        for index, item in enumerate(items):
            if self.fail_after is not None and index >= self.fail_after:
                raise GraphError("Graph GET answered 503", graph_status=503)
            yield item

    def history(self, graph_chat_id: str) -> AsyncIterator[dict[str, Any]]:
        self.asked.append(("history", graph_chat_id, None))
        return self._yield(self.history_items)

    def changed_since(
        self, graph_chat_id: str, since: datetime
    ) -> AsyncIterator[dict[str, Any]]:
        self.asked.append(("changes", graph_chat_id, since))
        return self._yield(self.changes)


async def _watched_chat(
    db: AsyncSession,
    watch: TeamsWatchState = TeamsWatchState.WATCHING,
    people: bool = True,
) -> TeamsGroup:
    """A chat linked to an active placement; with ``people``, its PS and a PMO
    manager (Entra ids are unique, so once per test)."""
    ps = User(
        email=f"ps-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Pia Sales",
        role=Role.PS.value,
        entra_oid=PS_OID,
    )
    manager = User(
        email=f"pm-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Pat Manager",
        role=Role.PMO_MANAGER.value,
        entra_oid=PMO_OID,
    )
    consultant = Consultant(full_name="Alex Sample")
    firm = Client(name=f"Demo {uuid.uuid4().hex[:6]}", normalized_name=uuid.uuid4().hex)
    db.add_all([ps, manager] if people else [])
    db.add_all([consultant, firm])
    await db.flush()
    project = Project(client_id=firm.id, name="Payments")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date(2026, 9, 1),
        expected_end_date=date(2027, 3, 31),
        status=PlacementStatus.ACTIVE.value,
        ps_user_id=ps.id if people else None,
    )
    db.add(placement)
    await db.flush()
    chat = TeamsGroup(
        graph_chat_id=f"19:{uuid.uuid4().hex}@thread.v2",
        title="PRJ ITC DS - Alex Sample - Demo - 1/9/2026 - 31/3/2027",
        match_status=TeamsChatMatch.MATCHED.value,
        placement_id=placement.id,
        watch_state=watch.value,
        watched_at=T0,
        consultant_member_oid=ALEX_OID,
    )
    db.add(chat)
    await db.flush()
    return chat


async def _messages(db: AsyncSession, chat_id: uuid.UUID) -> dict[str, Message]:
    rows = await db.execute(select(Message).where(Message.teams_group_id == chat_id))
    return {m.graph_message_id: m for m in rows.scalars()}


class TestHistory:
    async def test_the_first_sync_stores_the_whole_history(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _watched_chat(db_session)
        source = FakeMessages()
        source.history_items = [_msg(f"m{i}", i) for i in range(120)] + [
            _msg("sys", 200, author=None, kind="systemEventMessage")
        ]

        counts = await TeamsSync(db_session, source).sync(chat.id)

        assert counts is not None and counts.read == 121 and counts.added == 121
        assert source.asked == [("history", chat.graph_chat_id, None)]
        stored = await _messages(db_session, chat.id)
        assert len(stored) == 121
        assert all(m.is_history for m in stored.values())
        assert stored["sys"].message_type == "systemEventMessage"
        assert stored["sys"].author_role is None
        await db_session.refresh(chat)
        assert chat.history_state == HistoryState.STORED.value
        assert chat.last_synced_at is not None
        # The newest post, not the system event after it.
        assert chat.last_message_at == T0 + timedelta(minutes=119)

    async def test_authors_get_their_role_from_the_chat(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _watched_chat(db_session)
        source = FakeMessages()
        source.history_items = [
            _msg("a", 1, author=ALEX_OID),
            _msg("p", 2, author=PS_OID),
            _msg("m", 3, author=PMO_OID),
            _msg("g", 4, author=GUEST_OID),
        ]

        await TeamsSync(db_session, source).sync(chat.id)

        stored = await _messages(db_session, chat.id)
        assert {k: m.author_role for k, m in stored.items()} == {
            "a": "consultant",
            "p": "ps",
            "m": "pmo_manager",
            "g": "other",
        }


class TestChanges:
    async def test_later_syncs_read_changes_since_the_newest_stored_change(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _watched_chat(db_session)
        source = FakeMessages()
        source.history_items = [_msg("m1", 1), _msg("m2", 2), _msg("m3", 3)]
        await TeamsSync(db_session, source).sync(chat.id)

        source.changes = [
            _msg("m4", 10, text="new post"),
            _msg("m1", 1, text="edited text", modified=11),
            _msg("m2", 2, modified=12, deleted=12),
            _msg("m3", 3),  # read again in the overlap, unchanged
        ]
        counts = await TeamsSync(db_session, source).sync(chat.id)

        assert source.asked[-1] == (
            "changes",
            chat.graph_chat_id,
            T0 + timedelta(minutes=3) - WATERMARK_OVERLAP,
        )
        assert counts is not None
        assert (counts.read, counts.added, counts.edited, counts.deleted) == (
            4,
            1,
            1,
            1,
        )
        stored = await _messages(db_session, chat.id)
        assert stored["m4"].is_history is False
        assert stored["m4"].body_text == "new post"
        assert stored["m1"].body_text == "edited text"
        assert stored["m1"].last_modified_at == T0 + timedelta(minutes=11)
        assert stored["m2"].deleted_at == T0 + timedelta(minutes=12)
        assert stored["m2"].body_text == ""
        await db_session.refresh(chat)
        assert chat.last_message_at == T0 + timedelta(minutes=10)

    async def test_an_edit_is_looked_at_again_by_the_pipeline(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _watched_chat(db_session)
        source = FakeMessages()
        source.history_items = [_msg("m1", 1)]
        await TeamsSync(db_session, source).sync(chat.id)
        stored = (await _messages(db_session, chat.id))["m1"]
        stored.analysed_at = T0
        stored.message_class = "consultant_update"
        await db_session.flush()

        source.changes = [_msg("m1", 1, text="now blocked", modified=5)]
        await TeamsSync(db_session, source).sync(chat.id)

        await db_session.refresh(stored)
        assert stored.analysed_at is None and stored.message_class is None

    async def test_a_chat_with_no_message_reads_from_when_it_was_watched(
        self, db_session: AsyncSession
    ) -> None:
        chat = await _watched_chat(db_session)
        chat.history_state = HistoryState.STORED.value
        await db_session.flush()
        source = FakeMessages()

        await TeamsSync(db_session, source).sync(chat.id)

        assert source.asked == [("changes", chat.graph_chat_id, T0 - WATERMARK_OVERLAP)]


class TestNotRead:
    @pytest.mark.parametrize(
        "state",
        [TeamsWatchState.NOT_WATCHED, TeamsWatchState.STOPPED, TeamsWatchState.FAILED],
    )
    async def test_a_chat_not_watched_is_never_read(
        self, db_session: AsyncSession, state: TeamsWatchState
    ) -> None:
        chat = await _watched_chat(db_session, watch=state)
        source = FakeMessages()

        assert await TeamsSync(db_session, source).sync(chat.id) is None
        assert source.asked == []

    async def test_a_failed_read_stores_nothing(self, db_session: AsyncSession) -> None:
        chat = await _watched_chat(db_session)
        chat_id = chat.id
        await db_session.commit()
        source = FakeMessages()
        source.history_items = [_msg(f"m{i}", i) for i in range(10)]
        source.fail_after = 5

        with pytest.raises(GraphError):
            await TeamsSync(db_session, source).sync(chat_id)

        assert await _messages(db_session, chat_id) == {}
        after = await TeamsRepository(db_session).get_chat(chat_id)
        assert after is not None
        await db_session.refresh(after)
        assert after.history_state == HistoryState.NONE.value
        assert after.last_synced_at is None


class TestTakeoverQuery:
    async def test_chats_asked_to_sync_after_their_last_sync_are_found(
        self, db_session: AsyncSession
    ) -> None:
        unread = await _watched_chat(db_session)
        asked = await _watched_chat(db_session, people=False)
        done = await _watched_chat(db_session, people=False)
        stopped = await _watched_chat(
            db_session, watch=TeamsWatchState.STOPPED, people=False
        )
        for chat in (asked, done, stopped):
            chat.history_state = HistoryState.STORED.value
        asked.last_synced_at = T0
        asked.sync_requested_at = T0 + timedelta(seconds=1)
        done.last_synced_at = T0 + timedelta(seconds=1)
        done.sync_requested_at = T0
        stopped.sync_requested_at = T0
        await db_session.flush()

        found = set(await TeamsRepository(db_session).chats_needing_sync())

        assert {unread.id, asked.id} <= found
        assert done.id not in found and stopped.id not in found
