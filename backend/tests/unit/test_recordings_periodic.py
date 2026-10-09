"""When a scan runs: one queue job, deduplicated, queued by the loop and on request."""

import asyncio

import pytest

from app.services import processing_ownership, processing_queue
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    ProcessingQueue,
    set_processing_queue,
)
from app.services.recordings import periodic
from app.services.recordings.periodic import (
    SCAN_JOB_KIND,
    PeriodicRecordingsScan,
    register_recordings_scan,
    request_scan,
    scan_job,
)


@pytest.fixture
def queue() -> ProcessingQueue:
    fresh = ProcessingQueue(concurrency=1)
    set_processing_queue(fresh)
    yield fresh
    set_processing_queue(None)


class TestScanJob:
    def test_scan_is_one_fixed_backlog_job(self) -> None:
        assert scan_job() == scan_job()
        assert scan_job().kind == SCAN_JOB_KIND
        assert scan_job().priority == BACKLOG_PRIORITY

    def test_second_request_while_queued_is_not_queued_again(
        self, queue: ProcessingQueue
    ) -> None:
        assert request_scan() is True
        assert request_scan() is False
        assert queue.snapshot().depth == 1


class TestRegistration:
    def test_registers_the_runner_and_the_takeover_sweep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runners: dict[str, object] = {}
        sweeps: list[tuple[str, object]] = []
        monkeypatch.setattr(processing_queue, "_runners", runners)
        monkeypatch.setattr(processing_ownership, "_takeover_sweeps", sweeps)
        monkeypatch.setattr(periodic, "_registered", False)

        register_recordings_scan()
        register_recordings_scan()

        assert runners[SCAN_JOB_KIND] is periodic.run_scan_job
        # Once, however often the app starts.
        assert sweeps == [("recording scans", periodic.fail_interrupted_scans)]


class TestPeriodicRecordingsScan:
    async def test_queues_a_scan_at_start_and_each_interval(
        self, queue: ProcessingQueue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        requested: list[bool] = []
        three = asyncio.Event()

        def counting() -> bool:
            requested.append(request_scan())
            if len(requested) >= 3:
                three.set()
            return requested[-1]

        monkeypatch.setattr(periodic, "request_scan", counting)
        loop = PeriodicRecordingsScan(interval_seconds=1)
        loop._interval = 0.05  # type: ignore[assignment]
        loop.start()
        # Wait for the ticks rather than a fixed time, which a loaded
        # machine can overrun.
        await asyncio.wait_for(three.wait(), 5)
        await loop.stop()

        # The first request queues the job; later ones find it still queued
        # (no worker runs in this test) and add nothing.
        assert len(requested) >= 3
        assert requested[0] is True
        assert not any(requested[1:])
        assert queue.snapshot().depth == 1

    async def test_stop_ends_the_loop(self, queue: ProcessingQueue) -> None:
        loop = PeriodicRecordingsScan(interval_seconds=3600)
        loop.start()
        await asyncio.sleep(0)
        await loop.stop()
        assert loop._task is None
