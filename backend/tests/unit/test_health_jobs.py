"""The health jobs without a database: when the daily run falls (across the
clock changes), what a recompute job carries, and the daily loop."""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.enums import SnapshotReason
from app.services import health_jobs
from app.services import processing_queue as pq
from app.services.health_jobs import (
    DAILY_JOB_ID,
    DAILY_JOB_KIND,
    RECOMPUTE_JOB_KIND,
    DailyHealthRecompute,
    daily_job,
    last_daily_run,
    next_daily_run,
    recompute_job,
    request_recomputes,
    run_recompute_job,
)
from app.services.processing_queue import Job, ProcessingQueue

LONDON = ZoneInfo("Europe/London")


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestDailySchedule:
    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            # Summer: 06:00 BST is 05:00 UTC
            (_utc(2026, 10, 9, 4, 59), _utc(2026, 10, 9, 5, 0)),
            (_utc(2026, 10, 9, 5, 0), _utc(2026, 10, 10, 5, 0)),
            # The clocks go back on Sunday 25 October: 06:00 GMT is 06:00 UTC
            (_utc(2026, 10, 24, 5, 30), _utc(2026, 10, 25, 6, 0)),
            (_utc(2026, 10, 25, 5, 30), _utc(2026, 10, 25, 6, 0)),
            # The clocks go forward on Sunday 29 March: 06:00 BST is 05:00 UTC
            (_utc(2026, 3, 28, 6, 30), _utc(2026, 3, 29, 5, 0)),
            # 23:30 UTC is 00:30 the next day in London: that day's 06:00
            (_utc(2026, 10, 9, 23, 30), _utc(2026, 10, 10, 5, 0)),
        ],
    )
    def test_the_next_run_is_the_next_06_00_in_london(
        self, now: datetime, expected: datetime
    ) -> None:
        assert next_daily_run(now, 6, LONDON) == expected

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (_utc(2026, 10, 9, 5, 0), _utc(2026, 10, 9, 5, 0)),
            (_utc(2026, 10, 9, 4, 59), _utc(2026, 10, 8, 5, 0)),
            (_utc(2026, 10, 25, 7, 0), _utc(2026, 10, 25, 6, 0)),
            (_utc(2026, 10, 25, 5, 59), _utc(2026, 10, 24, 5, 0)),
        ],
    )
    def test_the_last_run_is_the_latest_06_00_at_or_before_now(
        self, now: datetime, expected: datetime
    ) -> None:
        assert last_daily_run(now, 6, LONDON) == expected


class TestJobs:
    @pytest.mark.parametrize(
        ("reason", "priority"),
        [
            (SnapshotReason.CALL, pq.SESSION_PRIORITY),
            (SnapshotReason.REGISTER, pq.SESSION_PRIORITY),
            (SnapshotReason.DAILY, pq.BACKLOG_PRIORITY),
            (SnapshotReason.CATCH_UP, pq.BACKLOG_PRIORITY),
        ],
    )
    def test_a_recompute_carries_its_reason_at_its_priority(
        self, reason: SnapshotReason, priority: int
    ) -> None:
        placement_id = uuid.uuid4()

        job = recompute_job(placement_id, reason)

        assert job == Job(RECOMPUTE_JOB_KIND, placement_id, priority, reason.value)

    def test_the_daily_job_has_one_fixed_id(self) -> None:
        assert daily_job() == daily_job()
        assert daily_job().kind == DAILY_JOB_KIND
        assert daily_job().id == DAILY_JOB_ID
        assert daily_job().priority == pq.BACKLOG_PRIORITY

    def test_requests_for_one_placement_make_one_job(self) -> None:
        queue = ProcessingQueue(concurrency=1)
        pq.set_processing_queue(queue)
        try:
            first, second = uuid.uuid4(), uuid.uuid4()
            queued = request_recomputes([first, second, first], SnapshotReason.DAILY)
            assert queued == 2
            assert request_recomputes([first], SnapshotReason.CALL) == 0
            assert [j.id for j in queue.snapshot().pending] == [first, second]
        finally:
            pq.set_processing_queue(None)

    async def test_a_recompute_without_a_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="without a reason"):
            await run_recompute_job(Job(RECOMPUTE_JOB_KIND, uuid.uuid4()))

    def test_registering_twice_is_harmless(self) -> None:
        health_jobs.register_health_processing()
        health_jobs.register_health_processing()

        assert pq._runners[RECOMPUTE_JOB_KIND] is health_jobs.run_recompute_job
        assert pq._runners[DAILY_JOB_KIND] is health_jobs.run_daily_job


class TestDailyLoop:
    async def test_the_daily_job_is_queued_when_the_hour_comes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queued = asyncio.Event()
        monkeypatch.setattr(health_jobs, "request_daily", queued.set)
        # A clock that reaches 06:00 London a moment after the loop starts
        due = _utc(2026, 10, 25, 6, 0)
        started = time.monotonic()

        def clock() -> datetime:
            elapsed = time.monotonic() - started
            return due - timedelta(seconds=0.2) + timedelta(seconds=elapsed)

        loop = DailyHealthRecompute(clock=clock)
        loop.start()
        try:
            await asyncio.wait_for(queued.wait(), timeout=10)
        finally:
            await loop.stop()

    async def test_stop_ends_a_loop_waiting_for_tomorrow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[None] = []
        monkeypatch.setattr(health_jobs, "request_daily", lambda: calls.append(None))
        loop = DailyHealthRecompute(clock=lambda: _utc(2026, 10, 9, 12, 0))
        loop.start()

        await asyncio.wait_for(loop.stop(), timeout=10)

        assert calls == []
