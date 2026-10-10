"""When health is recomputed: after a call, after a register edit, daily, at takeover.

Every recompute is a processing-queue job of kind ``health_recompute`` for one
placement, carrying its snapshot reason (``Job.reason``). The queue keeps one
job per placement, so a burst of requests makes one recompute, and a request
made while it runs makes one more run after it, so nothing is lost.

- **call**: the session job queues it after a completed analysis and its
  embeddings, never after a failed one.
- **register**: the register routes queue it after their commit (a placement
  created or edited; a project edited, for its active placements; a confirmed
  import, for the placements it created or changed).
- **daily**: with ``HEALTH_DAILY_ENABLED``, every task runs a loop that queues
  the ``health_daily`` job (one fixed id) at ``HEALTH_DAILY_HOUR`` in
  ``HEALTH_TIMEZONE``; its runner queues a recompute for every active
  placement. Only the task that owns processing runs queued jobs, so one task
  does it during a deploy.
- **catch_up**: at takeover, a placement with no snapshot (any status), or
  whose newest signal or register edit is newer than its latest snapshot, and
  (daily on) an active placement not recomputed since the last scheduled
  daily run, which a deploy across that hour would otherwise lose.

Calls and edits run at session priority (new evidence, quick to score); the
daily run and the catch-up at backlog priority.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.repositories.health_repo import HealthRepository
from app.db.repositories.placement_repo import PlacementRepository
from app.db.repositories.signal_repo import SignalRepository
from app.db.session import async_session_factory
from app.models.enums import PlacementStatus, SnapshotReason
from app.services.health_service import HealthService
from app.services.processing_ownership import register_takeover_requeue
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    SESSION_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)

logger = logging.getLogger(__name__)

RECOMPUTE_JOB_KIND = "health_recompute"
DAILY_JOB_KIND = "health_daily"
# Fixed so that every request for the daily run is the same job to the queue.
DAILY_JOB_ID = uuid.UUID("da11e000-0000-4000-8000-0000000000d1")

PRIORITY = {
    SnapshotReason.CALL: SESSION_PRIORITY,
    SnapshotReason.REGISTER: SESSION_PRIORITY,
    SnapshotReason.DAILY: BACKLOG_PRIORITY,
    SnapshotReason.CATCH_UP: BACKLOG_PRIORITY,
}

# The lifespan registers on every start; a test app starts many times.
_registered = False


def recompute_job(placement_id: uuid.UUID, reason: SnapshotReason) -> Job:
    return Job(
        kind=RECOMPUTE_JOB_KIND,
        id=placement_id,
        priority=PRIORITY[reason],
        reason=reason.value,
    )


def request_recompute(placement_id: uuid.UUID, reason: SnapshotReason) -> bool:
    """Queue the placement's recompute; False when one is already waiting."""
    return get_processing_queue().enqueue(recompute_job(placement_id, reason))


def request_recomputes(
    placement_ids: Iterable[uuid.UUID], reason: SnapshotReason
) -> int:
    """Queue a recompute per placement; how many were queued."""
    return sum(
        1 for pid in dict.fromkeys(placement_ids) if request_recompute(pid, reason)
    )


def daily_job() -> Job:
    return Job(
        kind=DAILY_JOB_KIND,
        id=DAILY_JOB_ID,
        priority=BACKLOG_PRIORITY,
        reason=SnapshotReason.DAILY.value,
    )


def request_daily() -> bool:
    return get_processing_queue().enqueue(daily_job())


async def run_recompute_job(job: Job) -> None:
    if job.reason is None:
        raise ValueError(f"Health recompute {job.id} was queued without a reason")
    async with async_session_factory() as db:
        await HealthService(db).recompute(job.id, SnapshotReason(job.reason))


async def run_daily_job(job: Job) -> None:
    async with async_session_factory() as db:
        placement_ids = await PlacementRepository(db).active_ids()
    queued = request_recomputes(placement_ids, SnapshotReason.DAILY)
    logger.info(
        "Daily health recompute: %d active placement(s), %d queued",
        len(placement_ids),
        queued,
    )


def last_daily_run(now: datetime, hour: int, tz: ZoneInfo) -> datetime:
    """The most recent scheduled daily run at or before ``now`` (in UTC)."""
    local = now.astimezone(tz)
    run = datetime.combine(local.date(), time(hour), tzinfo=tz)
    if run > local:
        run = datetime.combine(local.date() - timedelta(days=1), time(hour), tzinfo=tz)
    return run.astimezone(UTC)


def next_daily_run(now: datetime, hour: int, tz: ZoneInfo) -> datetime:
    """The first scheduled daily run after ``now`` (in UTC)."""
    local = now.astimezone(tz)
    run = datetime.combine(local.date(), time(hour), tzinfo=tz)
    if run <= local:
        run = datetime.combine(local.date() + timedelta(days=1), time(hour), tzinfo=tz)
    return run.astimezone(UTC)


async def stale_placements(now: datetime) -> list[uuid.UUID]:
    """The placements the takeover catch-up recomputes (see the module docstring)."""
    daily_cutoff = (
        last_daily_run(
            now, settings.health_daily_hour, ZoneInfo(settings.health_timezone)
        )
        if settings.health_daily_enabled
        else None
    )
    async with async_session_factory() as db:
        snapshots = await HealthRepository(db).latest_computed_at()
        newest_signal = await SignalRepository(db).latest_created_at()
        edits = await PlacementRepository(db).register_edits()
    stale: list[uuid.UUID] = []
    for placement_id, status, edited_at in edits:
        computed_at = snapshots.get(placement_id)
        signal_at = newest_signal.get(placement_id)
        if (
            computed_at is None
            or edited_at > computed_at
            or (signal_at is not None and signal_at > computed_at)
            or (
                daily_cutoff is not None
                and status == PlacementStatus.ACTIVE.value
                and computed_at < daily_cutoff
            )
        ):
            stale.append(placement_id)
    return stale


async def requeue_stale_placements() -> int:
    """Takeover re-queue: recompute the placements whose reading is out of date."""
    return request_recomputes(
        await stale_placements(datetime.now(UTC)), SnapshotReason.CATCH_UP
    )


def register_health_processing() -> None:
    """Register the health runners and the catch-up once; call before takeover."""
    global _registered
    if _registered:
        return
    register_runner(RECOMPUTE_JOB_KIND, run_recompute_job)
    register_runner(DAILY_JOB_KIND, run_daily_job)
    register_takeover_requeue("health catch-up", requeue_stale_placements)
    _registered = True


class DailyHealthRecompute:
    """Queues the daily recompute at ``HEALTH_DAILY_HOUR`` in ``HEALTH_TIMEZONE``."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._hour = settings.health_daily_hour
        self._tz = ZoneInfo(settings.health_timezone)
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="health-daily")
        logger.info(
            "Daily health recompute at %02d:00 %s, next at %s",
            self._hour,
            self._tz.key,
            next_daily_run(self._clock(), self._hour, self._tz).isoformat(),
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            due = next_daily_run(self._clock(), self._hour, self._tz)
            # Wait in steps of at most an hour, so a clock that moved (a
            # suspended laptop, a corrected host clock) is read again.
            while not self._stop.is_set():
                left = (due - self._clock()).total_seconds()
                if left <= 0:
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=min(left, 3600))
            if self._stop.is_set():
                return
            try:
                request_daily()
            except Exception:
                logger.exception("Could not queue the daily health recompute")
