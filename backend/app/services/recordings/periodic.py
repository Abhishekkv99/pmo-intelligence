"""When the recordings folder is scanned: every 15 minutes, and on request.

A scan is a processing-queue job of kind ``recordings_scan`` with one fixed
id. That gives the two guarantees a scan needs without any lock of its own:
the queue keeps one job per (kind, id), so a pass never overlaps another or
stacks up behind a slow one, and only the task that owns processing runs
queued jobs, so during a rolling deploy one task scans, not two. The loop
and "Scan now" only enqueue; a task waiting for ownership keeps its job
queued until it takes over. Backlog priority puts session work first.

A pass cut short by a shutdown leaves its ``recording_scans`` row
``running``; the next owner's takeover sweep marks it failed.
"""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime

from app.config import settings
from app.db.repositories.recording_repo import RecordingRepository
from app.db.session import async_session_factory
from app.services.processing_ownership import register_takeover_sweep
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)
from app.services.recordings.scanner import RecordingScanner

logger = logging.getLogger(__name__)

SCAN_JOB_KIND = "recordings_scan"
# Fixed so that every request for a scan is the same job to the queue.
SCAN_JOB_ID = uuid.UUID("5ca70000-0000-4000-8000-00000000f01d")

INTERRUPTED_REASON = "Interrupted by a restart before it finished"

# The lifespan registers on every start; a test app starts many times.
_registered = False


def scan_job() -> Job:
    return Job(kind=SCAN_JOB_KIND, id=SCAN_JOB_ID, priority=BACKLOG_PRIORITY)


def request_scan() -> bool:
    """Queue a scan; False when one is already waiting to start (one asked for
    during a running scan runs after it)."""
    return get_processing_queue().enqueue(scan_job())


async def run_scan_job(job: Job) -> None:
    async with async_session_factory() as session:
        await RecordingScanner(session).run()


async def fail_interrupted_scans() -> int:
    async with async_session_factory() as session:
        count = await RecordingRepository(session).fail_running_scans(
            datetime.now(UTC), INTERRUPTED_REASON
        )
        await session.commit()
    return count


def register_recordings_scan() -> None:
    """Register the scan's runner and takeover sweep once; call before takeover."""
    global _registered
    if _registered:
        return
    register_runner(SCAN_JOB_KIND, run_scan_job)
    register_takeover_sweep("recording scans", fail_interrupted_scans)
    _registered = True


class PeriodicRecordingsScan:
    """Queues a scan at start and then every ``interval_seconds``."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self._interval = interval_seconds or settings.recordings_scan_interval_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="recordings-scan")
        logger.info("Recordings scan every %d s", self._interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                request_scan()
            except Exception:
                logger.exception("Could not queue the recordings scan")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
