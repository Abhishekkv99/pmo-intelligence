"""Unit tests for the process-wide processing queue and its job runner."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest

from app.services import processing_queue as pq
from app.services.processing_queue import (
    Job,
    ProcessingQueue,
    get_processing_queue,
    job_key,
    register_runner,
    run_job,
    set_processing_queue,
)

pytestmark = pytest.mark.asyncio

QUEUE_MODULE = "app.services.processing_queue"


def _session(job_id: uuid.UUID | None = None) -> Job:
    return Job("session_pipeline", job_id or uuid.uuid4(), pq.SESSION_PRIORITY)


def _chat(job_id: uuid.UUID | None = None) -> Job:
    return Job("chat_pipeline", job_id or uuid.uuid4(), pq.CHAT_PRIORITY)


def _backlog() -> Job:
    return Job("health_recompute", uuid.uuid4(), pq.BACKLOG_PRIORITY)


class _Recorder:
    """A runner that records the order jobs ran in and can block on demand."""

    def __init__(self) -> None:
        self.ran: list[Job] = []
        self.gate: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.fail_on: set[Job] = set()

    async def __call__(self, job: Job) -> None:
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if job in self.fail_on:
            raise RuntimeError("boom")
        self.ran.append(job)


async def _drain(queue: ProcessingQueue) -> None:
    """Wait until every pending job has been taken and finished."""
    await queue._queue.join()


@pytest.fixture
async def started() -> AsyncGenerator[tuple[ProcessingQueue, _Recorder]]:
    recorder = _Recorder()
    queue = ProcessingQueue(concurrency=1, runner=recorder)
    await queue.start()
    yield queue, recorder
    await queue.stop()


class TestJobs:
    def test_chat_outranks_sessions_and_backlog_is_last(self) -> None:
        # Chat jobs are small and many and are where "live" comes from; a
        # backlog must never hold back newly arrived evidence.
        assert pq.CHAT_PRIORITY < pq.SESSION_PRIORITY < pq.BACKLOG_PRIORITY
        assert _chat().priority == pq.CHAT_PRIORITY
        assert _session().priority == pq.SESSION_PRIORITY
        assert _backlog().priority == pq.BACKLOG_PRIORITY

    def test_default_priority_is_session(self) -> None:
        assert Job("anything", uuid.uuid4()).priority == pq.SESSION_PRIORITY

    def test_key_is_kind_and_target_row(self) -> None:
        row_id = uuid.uuid4()
        assert job_key(_session(row_id)) == ("session_pipeline", row_id)
        assert job_key(_chat(row_id)) == ("chat_pipeline", row_id)

    def test_key_ignores_the_priority(self) -> None:
        # Otherwise the same work could sit in the queue twice, once at each
        # priority, and run twice.
        row_id = uuid.uuid4()
        normal = Job("health_recompute", row_id, pq.SESSION_PRIORITY)
        backlog = Job("health_recompute", row_id, pq.BACKLOG_PRIORITY)

        assert job_key(normal) == job_key(backlog)


class TestEnqueue:
    async def test_dedupes_a_pending_job(self) -> None:
        queue = ProcessingQueue(concurrency=1, runner=_Recorder())
        job = _session()

        assert queue.enqueue(job) is True
        assert queue.enqueue(_session(job.id)) is False
        assert queue.snapshot().depth == 1

    async def test_dedupes_across_priorities(self) -> None:
        queue = ProcessingQueue(concurrency=1, runner=_Recorder())
        row_id = uuid.uuid4()

        assert queue.enqueue(Job("health_recompute", row_id)) is True
        assert (
            queue.enqueue(Job("health_recompute", row_id, pq.BACKLOG_PRIORITY)) is False
        )

    async def test_two_kinds_for_one_row_are_distinct(self) -> None:
        queue = ProcessingQueue(concurrency=1, runner=_Recorder())
        row_id = uuid.uuid4()

        assert queue.enqueue(_session(row_id)) is True
        assert queue.enqueue(Job("health_recompute", row_id)) is True

    async def test_a_job_requested_while_it_runs_runs_once_more_after(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        recorder.gate = asyncio.Event()
        job = _session()

        queue.enqueue(job)
        await recorder.started.wait()
        assert queue.snapshot().running[0].job == job
        # Any number of requests during one run make one more run
        assert queue.enqueue(_session(job.id)) is True
        assert queue.enqueue(_session(job.id)) is True
        assert queue.snapshot().depth == 0

        recorder.gate.set()
        await _drain(queue)
        assert [j.id for j in recorder.ran] == [job.id, job.id]
        assert queue.enqueue(_session(job.id)) is True

    async def test_the_run_again_takes_the_latest_request(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        recorder.gate = asyncio.Event()
        job_id = uuid.uuid4()

        queue.enqueue(Job("health_recompute", job_id, pq.BACKLOG_PRIORITY, "daily"))
        await recorder.started.wait()
        queue.enqueue(Job("health_recompute", job_id, pq.BACKLOG_PRIORITY, "call"))
        queue.enqueue(Job("health_recompute", job_id, pq.SESSION_PRIORITY, "register"))
        recorder.gate.set()
        await _drain(queue)

        assert [(j.reason, j.priority) for j in recorder.ran] == [
            ("daily", pq.BACKLOG_PRIORITY),
            ("register", pq.SESSION_PRIORITY),
        ]

    async def test_a_failed_run_still_runs_again_when_requested(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        recorder.gate = asyncio.Event()
        job_id = uuid.uuid4()
        first = Job("health_recompute", job_id, reason="first")
        recorder.fail_on.add(first)

        queue.enqueue(first)
        await recorder.started.wait()
        queue.enqueue(Job("health_recompute", job_id, reason="second"))
        recorder.gate.set()
        await _drain(queue)

        assert [j.reason for j in recorder.ran] == ["second"]

    async def test_the_reason_is_not_part_of_a_job_s_identity(self) -> None:
        queue = ProcessingQueue(concurrency=1, runner=_Recorder())
        job_id = uuid.uuid4()

        assert queue.enqueue(Job("health_recompute", job_id, reason="call")) is True
        assert queue.enqueue(Job("health_recompute", job_id, reason="daily")) is False
        assert queue.snapshot().pending[0].reason == "call"

    async def test_snapshot_lists_pending_in_dispatch_order(self) -> None:
        queue = ProcessingQueue(concurrency=2, runner=_Recorder())
        first, second = _session(), _session()
        chat = _chat()
        queue.enqueue(first)
        queue.enqueue(second)
        queue.enqueue(chat)

        snapshot = queue.snapshot()

        assert snapshot.depth == 3
        assert snapshot.capacity == 2
        assert snapshot.running == ()
        assert snapshot.pending == (chat, first, second)


class TestDispatch:
    async def test_chat_runs_before_sessions_queued_earlier(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        # Hold the worker on a first job so the rest are ordered by the
        # queue rather than by arrival.
        recorder.gate = asyncio.Event()
        opener = _session()
        queue.enqueue(opener)
        await recorder.started.wait()

        session_a, session_b = _session(), _session()
        chat_a, chat_b = _chat(), _chat()
        for job in (session_a, session_b, chat_a, chat_b):
            queue.enqueue(job)
        recorder.gate.set()
        await _drain(queue)

        assert recorder.ran == [opener, chat_a, chat_b, session_a, session_b]

    async def test_a_new_arrival_overtakes_a_backlog_queued_earlier(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        # The case the backlog tier exists for: a backlog is already waiting
        # when a fresh recording arrives. The new one runs next, not after
        # the whole backlog.
        queue, recorder = started
        recorder.gate = asyncio.Event()
        opener = _session()
        queue.enqueue(opener)
        await recorder.started.wait()

        backlog = [_backlog() for _ in range(3)]
        for job in backlog:
            queue.enqueue(job)
        new_arrival = _session()
        queue.enqueue(new_arrival)
        recorder.gate.set()
        await _drain(queue)

        assert recorder.ran == [opener, new_arrival, *backlog]

    async def test_chat_still_outranks_a_new_session(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        recorder.gate = asyncio.Event()
        opener = _session()
        queue.enqueue(opener)
        await recorder.started.wait()

        backlog = _backlog()
        new_session = _session()
        chat = _chat()
        for job in (backlog, new_session, chat):
            queue.enqueue(job)
        recorder.gate.set()
        await _drain(queue)

        assert recorder.ran == [opener, chat, new_session, backlog]

    async def test_fifo_within_a_class(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        jobs = [_session() for _ in range(5)]
        for job in jobs:
            queue.enqueue(job)

        await _drain(queue)

        assert recorder.ran == jobs


class TestWorker:
    async def test_a_failing_job_does_not_stop_the_worker(
        self,
        started: tuple[ProcessingQueue, _Recorder],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        queue, recorder = started
        bad, good = _session(), _session()
        recorder.fail_on = {bad}

        with caplog.at_level("ERROR", logger=QUEUE_MODULE):
            queue.enqueue(bad)
            queue.enqueue(good)
            await _drain(queue)

        assert recorder.ran == [good]
        assert f"Processing job session_pipeline {bad.id} failed" in caplog.text
        assert queue.snapshot().running == ()

    async def test_running_shows_the_job_and_its_worker(
        self, started: tuple[ProcessingQueue, _Recorder]
    ) -> None:
        queue, recorder = started
        recorder.gate = asyncio.Event()
        job = _session()
        queue.enqueue(job)
        await recorder.started.wait()

        (running,) = queue.snapshot().running
        assert running.job == job
        assert running.worker == 0
        assert running.started_at.tzinfo is not None
        assert queue.snapshot().depth == 0

        recorder.gate.set()
        await _drain(queue)
        assert queue.snapshot().running == ()

    async def test_capacity_runs_that_many_jobs_at_once(self) -> None:
        recorder = _Recorder()
        recorder.gate = asyncio.Event()
        queue = ProcessingQueue(concurrency=2, runner=recorder)
        await queue.start()
        try:
            for _ in range(3):
                queue.enqueue(_session())
            await recorder.started.wait()
            await asyncio.sleep(0)

            snapshot = queue.snapshot()
            assert len(snapshot.running) == 2
            assert snapshot.depth == 1
            assert {r.worker for r in snapshot.running} == {0, 1}
        finally:
            recorder.gate.set()
            await queue.stop()

    async def test_stop_cancels_a_blocked_job_without_draining(self) -> None:
        recorder = _Recorder()
        recorder.gate = asyncio.Event()  # never set: the job blocks forever
        queue = ProcessingQueue(concurrency=1, runner=recorder)
        await queue.start()
        queue.enqueue(_session())
        queue.enqueue(_session())
        await recorder.started.wait()

        await queue.stop()

        assert queue.is_running is False
        assert recorder.ran == []
        # Neither the cancelled job nor the one behind it ran; the takeover
        # sweeps make their rows retryable.
        assert queue.snapshot().depth == 1

    async def test_stop_drops_a_booked_run_again(self) -> None:
        recorder = _Recorder()
        recorder.gate = asyncio.Event()  # never set: the job blocks forever
        queue = ProcessingQueue(concurrency=1, runner=recorder)
        await queue.start()
        job = _session()
        queue.enqueue(job)
        await recorder.started.wait()
        queue.enqueue(_session(job.id))

        await queue.stop()

        assert queue.snapshot().depth == 0
        assert queue.is_queued(job) is False

    async def test_start_is_idempotent_and_capacity_floors_at_one(self) -> None:
        queue = ProcessingQueue(concurrency=0, runner=_Recorder())
        assert queue.capacity == 1
        await queue.start()
        workers = list(queue._workers)
        await queue.start()
        try:
            assert queue._workers == workers
        finally:
            await queue.stop()

    async def test_default_capacity_comes_from_settings(self) -> None:
        with patch(f"{QUEUE_MODULE}.settings") as settings:
            settings.processing_concurrency = 3
            assert ProcessingQueue().capacity == 3


class TestStragglers:
    async def test_a_worker_that_outlives_stop_is_waited_for(self) -> None:
        """A job frozen on a dead DB connection can ignore cancellation.

        The queue must keep counting it as running and let the caller wait for
        it, rather than start new workers alongside it ("6 of 3").
        """
        release = asyncio.Event()
        entered = asyncio.Event()

        async def frozen(job: Job) -> None:
            entered.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await release.wait()  # blocked I/O: ends only when it returns
                raise

        queue = ProcessingQueue(concurrency=1, runner=frozen)
        queue.STOP_GRACE_SECONDS = 0.05
        await queue.start()
        queue.enqueue(_session())
        await asyncio.wait_for(entered.wait(), 1)

        await queue.stop()
        assert len(queue.snapshot().running) == 1  # still really running

        waiting = asyncio.create_task(queue.wait_for_stragglers(log_every=0.05))
        await asyncio.sleep(0.2)
        assert not waiting.done()

        release.set()
        await asyncio.wait_for(waiting, 1)
        assert queue.snapshot().running == ()

    async def test_nothing_to_wait_for_after_a_clean_stop(self) -> None:
        queue = ProcessingQueue(concurrency=2, runner=AsyncMock())
        await queue.start()
        await queue.stop()
        await asyncio.wait_for(queue.wait_for_stragglers(), 1)


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the module-level runner registry for one test."""
    monkeypatch.setattr(pq, "_runners", {})


@pytest.mark.usefixtures("empty_registry")
class TestRunJob:
    async def test_dispatches_to_the_runner_registered_for_the_kind(self) -> None:
        session_runner, chat_runner = AsyncMock(), AsyncMock()
        register_runner("session_pipeline", session_runner)
        register_runner("chat_pipeline", chat_runner)
        job = _chat()

        await run_job(job)

        chat_runner.assert_awaited_once_with(job)
        session_runner.assert_not_awaited()

    async def test_an_unregistered_kind_raises(self) -> None:
        with pytest.raises(LookupError, match="unknown_kind"):
            await run_job(Job("unknown_kind", uuid.uuid4()))

    async def test_a_second_runner_for_a_kind_is_refused(self) -> None:
        register_runner("session_pipeline", AsyncMock())
        with pytest.raises(ValueError, match="already registered"):
            register_runner("session_pipeline", AsyncMock())

    async def test_registering_the_same_runner_again_is_harmless(self) -> None:
        runner = AsyncMock()
        register_runner("session_pipeline", runner)
        register_runner("session_pipeline", runner)

        await run_job(_session())
        runner.assert_awaited_once()

    async def test_the_default_queue_runs_jobs_through_the_registry(self) -> None:
        runner = AsyncMock()
        register_runner("session_pipeline", runner)
        queue = ProcessingQueue(concurrency=1)
        await queue.start()
        try:
            job = _session()
            queue.enqueue(job)
            await _drain(queue)
        finally:
            await queue.stop()

        runner.assert_awaited_once_with(job)


class TestSingleton:
    def test_get_creates_once_and_set_replaces(self) -> None:
        set_processing_queue(None)
        first = get_processing_queue()
        assert get_processing_queue() is first

        replacement = ProcessingQueue(concurrency=1, runner=_Recorder())
        set_processing_queue(replacement)
        assert get_processing_queue() is replacement
