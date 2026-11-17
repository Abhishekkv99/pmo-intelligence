"""When Teams work runs: discovery, subscription reviews and syncs as queue
jobs, queued by the loops, on request and on takeover."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest

from app.config import settings
from app.services import processing_ownership, processing_queue
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    CHAT_PRIORITY,
    SESSION_PRIORITY,
    Job,
    ProcessingQueue,
    set_processing_queue,
)
from app.services.teams import jobs
from app.services.teams.jobs import (
    DISCOVERY_JOB_KIND,
    SUBSCRIPTION_JOB_KIND,
    SYNC_JOB_KIND,
    PeriodicTeamsDiscovery,
    PeriodicTeamsUpkeep,
    discovery_job,
    register_teams_processing,
    request_discovery,
    request_subscription_review,
    request_sync,
)
from app.services.teams.subscriptions import Ask, Outcome


@pytest.fixture
def queue() -> Iterator[ProcessingQueue]:
    fresh = ProcessingQueue(concurrency=1)
    set_processing_queue(fresh)
    yield fresh
    set_processing_queue(None)


class TestDiscoveryJob:
    def test_discovery_is_one_fixed_backlog_job(self) -> None:
        assert discovery_job() == discovery_job()
        assert discovery_job().kind == DISCOVERY_JOB_KIND
        assert discovery_job().priority == BACKLOG_PRIORITY

    def test_second_request_while_queued_is_not_queued_again(
        self, queue: ProcessingQueue
    ) -> None:
        assert request_discovery() is True
        assert request_discovery() is False
        assert queue.snapshot().depth == 1


class TestRegistration:
    def test_registers_the_runner_and_the_takeover_sweep_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runners: dict[str, object] = {}
        sweeps: list[tuple[str, object]] = []
        requeues: list[tuple[str, object]] = []
        monkeypatch.setattr(processing_queue, "_runners", runners)
        monkeypatch.setattr(processing_ownership, "_takeover_sweeps", sweeps)
        monkeypatch.setattr(processing_ownership, "_takeover_requeues", requeues)
        monkeypatch.setattr(jobs, "_registered", False)

        register_teams_processing()
        register_teams_processing()

        assert runners[DISCOVERY_JOB_KIND] is jobs.run_discovery_job
        assert runners[SYNC_JOB_KIND] is jobs.run_sync_job
        assert runners[SUBSCRIPTION_JOB_KIND] is jobs.run_subscription_job
        assert sweeps == [("teams scans", jobs.fail_interrupted_scans)]
        assert requeues == [("teams syncs", jobs.requeue_requested_syncs)]


class TestPeriodicTeamsDiscovery:
    async def test_queues_discovery_at_start_and_each_interval(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        requested: list[bool] = []
        three = asyncio.Event()

        def counting() -> bool:
            requested.append(request_discovery())
            if len(requested) >= 3:
                three.set()
            return requested[-1]

        monkeypatch.setattr(jobs, "request_discovery", counting)
        loop = PeriodicTeamsDiscovery(interval_seconds=1)
        loop._interval = 0.05  # type: ignore[assignment]
        loop.start()
        await asyncio.wait_for(three.wait(), 5)
        await loop.stop()

        assert len(requested) >= 3
        assert requested[0] is True
        assert not any(requested[1:])
        assert queue.snapshot().depth == 1

    async def test_stop_ends_the_loop(self, queue: ProcessingQueue) -> None:
        loop = PeriodicTeamsDiscovery(interval_seconds=3600)
        loop.start()
        await asyncio.sleep(0)
        await loop.stop()
        assert loop._task is None


CHAT_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
CHAT_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")


class TestSyncAndSubscriptionJobs:
    def test_nothing_is_queued_while_teams_is_off(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", False)
        assert request_sync([CHAT_A]) == 0
        assert request_subscription_review([CHAT_A]) == 0
        assert queue.snapshot().depth == 0

    def test_a_sync_is_one_chat_priority_job_per_chat(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        assert request_sync([CHAT_A, CHAT_A, CHAT_B]) == 2
        assert request_sync([CHAT_A]) == 0
        assert {(j.kind, j.id, j.priority) for j in queue.snapshot().pending} == {
            (SYNC_JOB_KIND, CHAT_A, CHAT_PRIORITY),
            (SYNC_JOB_KIND, CHAT_B, CHAT_PRIORITY),
        }

    def test_a_review_carries_what_graph_asked_for(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        assert request_subscription_review([CHAT_A], Ask.RENEW) == 1
        (job,) = queue.snapshot().pending
        assert (job.kind, job.priority, job.reason) == (
            SUBSCRIPTION_JOB_KIND,
            SESSION_PRIORITY,
            "renew",
        )

    @pytest.mark.parametrize(
        ("outcome", "synced"),
        [(Outcome.CREATED, [[CHAT_A]]), (Outcome.RENEWED, []), (Outcome.KEPT, [])],
    )
    async def test_a_new_subscription_asks_for_a_sync(
        self,
        monkeypatch: pytest.MonkeyPatch,
        outcome: Outcome,
        synced: list[list[uuid.UUID]],
    ) -> None:
        asked: list[tuple[uuid.UUID, Ask | None]] = []
        recorded: list[list[uuid.UUID]] = []

        class FakeSubscriptions:
            def __init__(self, session: object) -> None:
                pass

            async def review(self, chat_id: uuid.UUID, ask: Ask | None) -> Outcome:
                asked.append((chat_id, ask))
                return outcome

        async def record(chat_ids: list[uuid.UUID]) -> int:
            recorded.append(chat_ids)
            return len(chat_ids)

        @asynccontextmanager
        async def no_session() -> AsyncIterator[None]:
            yield None

        monkeypatch.setattr(jobs, "TeamsSubscriptions", FakeSubscriptions)
        monkeypatch.setattr(jobs, "record_and_request_sync", record)
        monkeypatch.setattr(jobs, "async_session_factory", no_session)

        await jobs.run_subscription_job(
            Job(kind=SUBSCRIPTION_JOB_KIND, id=CHAT_A, reason="recreate")
        )

        assert asked == [(CHAT_A, Ask.RECREATE)]
        assert recorded == synced


class TestPeriodicTeamsUpkeep:
    async def test_reviews_every_tick_and_catches_up_once_a_day(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "teams_enabled", True)
        caught_up: list[list[uuid.UUID]] = []

        class FakeRepo:
            def __init__(self, session: object) -> None:
                pass

            async def subscribed_or_watching_chat_ids(self) -> list[uuid.UUID]:
                return [CHAT_A, CHAT_B]

            async def watching_chat_ids(self) -> list[uuid.UUID]:
                return [CHAT_A]

        async def record(chat_ids: list[uuid.UUID]) -> int:
            caught_up.append(chat_ids)
            return len(chat_ids)

        @asynccontextmanager
        async def no_session() -> AsyncIterator[None]:
            yield None

        monkeypatch.setattr(jobs, "TeamsRepository", FakeRepo)
        monkeypatch.setattr(jobs, "async_session_factory", no_session)
        monkeypatch.setattr(jobs, "record_and_request_sync", record)
        upkeep = PeriodicTeamsUpkeep(interval_seconds=21_600, catch_up_seconds=86_400)

        await upkeep.tick(0.0)
        await upkeep.tick(21_600.0)
        await upkeep.tick(86_400.0)

        assert caught_up == [[CHAT_A], [CHAT_A]]
        assert {(j.kind, j.id) for j in queue.snapshot().pending} == {
            (SUBSCRIPTION_JOB_KIND, CHAT_A),
            (SUBSCRIPTION_JOB_KIND, CHAT_B),
        }

    async def test_stop_ends_the_loop(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ticks: list[float] = []

        async def tick(now: float) -> None:
            ticks.append(now)

        upkeep = PeriodicTeamsUpkeep(interval_seconds=3600)
        monkeypatch.setattr(upkeep, "tick", tick)
        upkeep.start()
        await asyncio.sleep(0.01)
        await upkeep.stop()
        assert upkeep._task is None
        assert len(ticks) == 1
