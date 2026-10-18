"""When discovery runs: one fixed queue job, queued by the loop and on request."""

import asyncio
from collections.abc import Iterator

import pytest

from app.services import processing_ownership, processing_queue
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    ProcessingQueue,
    set_processing_queue,
)
from app.services.teams import jobs
from app.services.teams.jobs import (
    DISCOVERY_JOB_KIND,
    PeriodicTeamsDiscovery,
    discovery_job,
    register_teams_processing,
    request_discovery,
)


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
        monkeypatch.setattr(processing_queue, "_runners", runners)
        monkeypatch.setattr(processing_ownership, "_takeover_sweeps", sweeps)
        monkeypatch.setattr(jobs, "_registered", False)

        register_teams_processing()
        register_teams_processing()

        assert runners[DISCOVERY_JOB_KIND] is jobs.run_discovery_job
        assert sweeps == [("teams scans", jobs.fail_interrupted_scans)]


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
