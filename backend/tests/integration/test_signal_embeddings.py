"""Signal embeddings against a real database, with a fake Azure client.

A session's signals without an embedding are embedded in batches, written
with a cost row per request in one commit; a failure, a wrong answer or a
timeout writes nothing and, through ``embed_session_signals``, never raises.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
from openai import AsyncAzureOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import JobStatus, SessionStatus
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session
from app.models.signal import Signal
from app.services import signal_embeddings
from app.services.cost_tracker import calculate_embedding_cost
from app.services.signal_embeddings import (
    EMBEDDING_OPERATION,
    EmbeddingError,
    SignalEmbeddingService,
    embed_session_signals,
)
from tests.unit.embedding_helpers import (
    TOKENS_PER_INPUT,
    FakeEmbeddingClient,
    vector,
)

HELD_AT = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)


class Called:
    """The rows, and their ids kept apart: a rollback expires the rows."""

    def __init__(self, session: Session, job: ProcessingJob) -> None:
        self.session = session
        self.job = job
        self.session_id = session.id
        self.job_id = job.id


@pytest.fixture
async def called(db_session: AsyncSession) -> Called:
    """A completed session with its job; committed, so a rollback keeps it."""
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
    session = Session(
        placement_id=placement.id,
        held_at=HELD_AT,
        source="upload",
        status=SessionStatus.COMPLETED.value,
    )
    db_session.add(session)
    await db_session.flush()
    job = ProcessingJob(
        kind="session", subject_id=session.id, status=JobStatus.COMPLETED.value
    )
    db_session.add(job)
    await db_session.commit()
    return Called(session, job)


async def _signals(
    db: AsyncSession, called: Called, notes: list[str | None]
) -> list[Signal]:
    rows = [
        Signal(
            placement_id=called.session.placement_id,
            source_kind="session",
            source_id=called.session.id,
            category="client",
            dimension="delivery",
            polarity="negative",
            severity=2,
            confidence=0.8,
            quote=f"Quote {n}.",
            note=note,
            occurred_at=HELD_AT + timedelta(seconds=n),
            offset_ms=n * 1000,
        )
        for n, note in enumerate(notes)
    ]
    db.add_all(rows)
    await db.commit()
    return rows


async def _costs(db: AsyncSession, called: Called) -> list[ProcessingCost]:
    return list(
        (
            await db.scalars(
                select(ProcessingCost)
                .where(ProcessingCost.session_id == called.session_id)
                .order_by(ProcessingCost.created_at, ProcessingCost.id)
            )
        ).all()
    )


def _service(db: AsyncSession, client: FakeEmbeddingClient) -> SignalEmbeddingService:
    return SignalEmbeddingService(db, client=cast(AsyncAzureOpenAI, client))


def _vector(row: Signal) -> list[float] | None:
    """The stored vector as plain floats (pgvector reads back a numpy array)."""
    return None if row.embedding is None else [float(x) for x in row.embedding]


async def _embeddings(db: AsyncSession, rows: list[Signal]) -> list[bool]:
    for row in rows:
        await db.refresh(row)
    return [row.embedding is not None for row in rows]


class TestEmbedSession:
    async def test_every_signal_is_embedded_and_the_request_costed(
        self,
        db_session: AsyncSession,
        called: Called,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "azure_embedding_deployment", "embed-test")
        rows = await _signals(db_session, called, ["Late again.", None])
        client = FakeEmbeddingClient()

        count = await _service(db_session, client).embed_session(
            called.session.id, called.job.id
        )

        assert count == 2
        assert client.embeddings.requests == [
            {"model": "embed-test", "input": ["Quote 0.\nLate again.", "Quote 1."]}
        ]
        for row in rows:
            await db_session.refresh(row)
        # Each vector lands on its own signal, whatever order Azure answers in
        assert [_vector(row) for row in rows] == [vector(0), vector(1)]
        [cost] = await _costs(db_session, called)
        assert cost.service == "azure_openai"
        assert cost.operation == EMBEDDING_OPERATION
        assert cost.input_tokens == 2 * TOKENS_PER_INPUT
        assert cost.amount_usd == pytest.approx(
            calculate_embedding_cost(2 * TOKENS_PER_INPUT)
        )
        assert cost.model == "embed-test"
        assert cost.processing_job_id == called.job.id
        assert cost.duration_seconds is not None

    async def test_signals_are_sent_in_batches_with_a_cost_row_each(
        self,
        db_session: AsyncSession,
        called: Called,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "signal_embedding_batch_size", 2)
        rows = await _signals(db_session, called, ["a", "b", "c"])
        client = FakeEmbeddingClient()

        await _service(db_session, client).embed_session(called.session.id)

        assert [len(r["input"]) for r in client.embeddings.requests] == [2, 1]
        assert len(await _costs(db_session, called)) == 2
        assert await _embeddings(db_session, rows) == [True, True, True]

    async def test_only_signals_without_an_embedding_are_sent(
        self, db_session: AsyncSession, called: Called
    ) -> None:
        done, waiting = await _signals(db_session, called, ["a", "b"])
        done.embedding = vector(7)
        await db_session.commit()
        client = FakeEmbeddingClient()

        count = await _service(db_session, client).embed_session(called.session.id)

        assert count == 1
        assert client.embeddings.requests[0]["input"] == ["Quote 1.\nb"]
        await db_session.refresh(done)
        assert _vector(done) == vector(7)

    async def test_a_session_without_signals_makes_no_request(
        self, db_session: AsyncSession, called: Called
    ) -> None:
        client = FakeEmbeddingClient()

        count = await _service(db_session, client).embed_session(called.session.id)

        assert count == 0
        assert client.embeddings.requests == []
        assert await _costs(db_session, called) == []

    @pytest.mark.parametrize(
        "client",
        [
            FakeEmbeddingClient(missing=1),
            FakeEmbeddingClient(dimensions=3),
        ],
        ids=["a vector missing", "wrong dimensions"],
    )
    async def test_an_answer_that_does_not_fit_raises(
        self,
        db_session: AsyncSession,
        called: Called,
        client: FakeEmbeddingClient,
    ) -> None:
        await _signals(db_session, called, ["a", "b"])

        with pytest.raises(EmbeddingError):
            await _service(db_session, client).embed_session(called.session.id)


class TestNeverFailsTheSession:
    @pytest.mark.parametrize(
        "options",
        [
            {"error": RuntimeError("Azure unavailable")},
            {"missing": 1},
            {"hang": True},
        ],
        ids=["error", "wrong answer", "timeout"],
    )
    # The first batch succeeds, the second fails: the session's embeddings are
    # written all at once or not at all
    async def test_a_failure_writes_nothing_and_does_not_raise(
        self,
        db_session: AsyncSession,
        called: Called,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        options: dict[str, object],
    ) -> None:
        monkeypatch.setattr(settings, "signal_embedding_batch_size", 1)
        monkeypatch.setattr(settings, "signal_embedding_timeout_seconds", 0.2)
        rows = await _signals(db_session, called, ["a", "b"])
        client = FakeEmbeddingClient(bad_requests={2}, **options)
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        await embed_session_signals(db_session, called.session_id, called.job_id)

        assert len(client.embeddings.requests) == 2
        assert await _embeddings(db_session, rows) == [False, False]
        assert await _costs(db_session, called) == []
        assert "stay empty until the backfill command is run" in caplog.text
        await db_session.refresh(called.session)
        assert called.session.status == SessionStatus.COMPLETED.value

    async def test_a_success_is_logged_with_the_count(
        self,
        db_session: AsyncSession,
        called: Called,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level("INFO", logger=signal_embeddings.__name__)
        rows = await _signals(db_session, called, ["a"])
        client = FakeEmbeddingClient()
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)

        await embed_session_signals(db_session, called.session_id, called.job_id)

        assert await _embeddings(db_session, rows) == [True]
        assert "1 signal(s) embedded" in caplog.text
