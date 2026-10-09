"""The embedding backfill against a real database, with a fake Azure client:
every session with a signal not yet embedded, oldest call first, each in its
own commit; a session that fails is skipped and makes the exit code 1."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.backfill_signal_embeddings import SessionFactory, backfill
from app.models.processing_cost import ProcessingCost
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session
from app.models.signal import Signal
from app.services import signal_embeddings
from tests.unit.embedding_helpers import FakeEmbeddingClient, vector

HELD_AT = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)


@pytest.fixture
async def placement_id(db_session: AsyncSession) -> uuid.UUID:
    client = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
    consultant = Consultant(full_name="Priya Shah")
    db_session.add_all([client, consultant])
    await db_session.flush()
    project = Project(client_id=client.id, name="Data platform")
    db_session.add(project)
    await db_session.flush()
    placement = Placement(
        consultant_id=consultant.id, project_id=project.id, start_date=date(2026, 9, 1)
    )
    db_session.add(placement)
    await db_session.flush()
    return placement.id


@pytest.fixture
def factory(db_session: AsyncSession) -> SessionFactory:
    """The backfill's session factory, handing out the test's session."""

    @asynccontextmanager
    async def same() -> AsyncIterator[AsyncSession]:
        yield db_session

    return same


async def _session_with_signals(
    db: AsyncSession,
    placement_id: uuid.UUID,
    held_at: datetime,
    *,
    embedded: list[bool],
) -> uuid.UUID:
    session = Session(
        placement_id=placement_id, held_at=held_at, source="upload", status="completed"
    )
    db.add(session)
    await db.flush()
    db.add_all(
        Signal(
            placement_id=placement_id,
            source_kind="session",
            source_id=session.id,
            category="client",
            dimension="delivery",
            polarity="negative",
            severity=2,
            confidence=0.8,
            quote=f"Quote {n} on {held_at:%d %B}.",
            occurred_at=held_at + timedelta(seconds=n),
            offset_ms=n * 1000,
            embedding=vector(99) if done else None,
        )
        for n, done in enumerate(embedded)
    )
    await db.commit()
    return session.id


async def _missing(db: AsyncSession, session_id: uuid.UUID) -> int:
    rows = await db.scalars(
        select(Signal)
        .where(Signal.source_id == session_id, Signal.embedding.is_(None))
        .execution_options(populate_existing=True)
    )
    return len(rows.all())


async def _costs(db: AsyncSession, session_id: uuid.UUID) -> int:
    rows = await db.scalars(
        select(ProcessingCost).where(ProcessingCost.session_id == session_id)
    )
    return len(rows.all())


class TestBackfill:
    async def test_every_session_missing_embeddings_is_filled_oldest_first(
        self,
        db_session: AsyncSession,
        placement_id: uuid.UUID,
        factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        later = await _session_with_signals(
            db_session, placement_id, HELD_AT, embedded=[False]
        )
        earlier = await _session_with_signals(
            db_session,
            placement_id,
            HELD_AT - timedelta(days=7),
            embedded=[True, False],
        )
        done = await _session_with_signals(
            db_session, placement_id, HELD_AT - timedelta(days=14), embedded=[True]
        )
        client = FakeEmbeddingClient()
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        assert await backfill(dry_run=False, session_factory=factory) == 0

        assert [r["input"] for r in client.embeddings.requests] == [
            ["Quote 1 on 29 September."],
            ["Quote 0 on 06 October."],
        ]
        for session_id in (later, earlier, done):
            assert await _missing(db_session, session_id) == 0
        assert [await _costs(db_session, s) for s in (later, earlier, done)] == [
            1,
            1,
            0,
        ]

    async def test_a_dry_run_counts_and_sends_nothing(
        self,
        db_session: AsyncSession,
        placement_id: uuid.UUID,
        factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level("INFO", logger="backfill_signal_embeddings")
        session_id = await _session_with_signals(
            db_session, placement_id, HELD_AT, embedded=[False, False, True]
        )
        client = FakeEmbeddingClient()
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        assert await backfill(dry_run=True, session_factory=factory) == 0

        assert client.embeddings.requests == []
        assert await _missing(db_session, session_id) == 2
        assert "2 signal(s) in 1 session(s) have no embedding" in caplog.text

    async def test_a_failed_session_is_skipped_and_the_exit_code_is_1(
        self,
        db_session: AsyncSession,
        placement_id: uuid.UUID,
        factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        first = await _session_with_signals(
            db_session, placement_id, HELD_AT - timedelta(days=7), embedded=[False]
        )
        second = await _session_with_signals(
            db_session, placement_id, HELD_AT, embedded=[False]
        )
        third = await _session_with_signals(
            db_session, placement_id, HELD_AT + timedelta(days=7), embedded=[False]
        )
        # The second session's request fails; the first and third succeed
        client = FakeEmbeddingClient(
            bad_requests={2}, error=RuntimeError("Azure unavailable")
        )
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        assert await backfill(dry_run=False, session_factory=factory) == 1

        assert [await _missing(db_session, s) for s in (first, second, third)] == [
            0,
            1,
            0,
        ]
        assert [await _costs(db_session, s) for s in (first, second, third)] == [
            1,
            0,
            1,
        ]

    async def test_nothing_missing_sends_nothing(
        self,
        db_session: AsyncSession,
        placement_id: uuid.UUID,
        factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _session_with_signals(db_session, placement_id, HELD_AT, embedded=[True])
        client = FakeEmbeddingClient()
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        assert await backfill(dry_run=False, session_factory=factory) == 0

        assert client.embeddings.requests == []
