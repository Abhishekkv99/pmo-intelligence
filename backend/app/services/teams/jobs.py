"""When Teams chat work runs: discovery at start, daily, and on request.

Discovery is a processing-queue job of kind ``teams_discovery`` with one fixed
id, as the recordings scan is: the queue keeps one job per (kind, id), so a
pass never overlaps another, and only the task that owns processing runs it.
The loop and "Scan now" only enqueue. Backlog priority puts session and chat
work first.

A pass cut short by a shutdown leaves its ``teams_scans`` row ``running``; the
next owner's takeover sweep marks it failed.
"""

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.db.session import async_session_factory
from app.services.processing_ownership import register_takeover_sweep
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)
from app.services.teams.discovery import TeamsDiscovery

logger = logging.getLogger(__name__)

DISCOVERY_JOB_KIND = "teams_discovery"
# Fixed so that every request for discovery is the same job to the queue.
DISCOVERY_JOB_ID = uuid.UUID("7ea50000-0000-4000-8000-00000000d15c")

INTERRUPTED_REASON = "Interrupted by a restart before it finished"

# The lifespan registers on every start; a test app starts many times.
_registered = False


def discovery_job() -> Job:
    return Job(kind=DISCOVERY_JOB_KIND, id=DISCOVERY_JOB_ID, priority=BACKLOG_PRIORITY)


def request_discovery() -> bool:
    """Queue discovery; False when a pass is already waiting to start (one asked
    for during a running pass runs after it)."""
    return get_processing_queue().enqueue(discovery_job())


async def run_discovery_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsDiscovery(session).run()


async def fail_interrupted_scans() -> int:
    async with async_session_factory() as session:
        count = await TeamsRepository(session).fail_running_scans(
            datetime.now(UTC), INTERRUPTED_REASON
        )
        await session.commit()
    return count


def register_teams_processing() -> None:
    """Register the Teams runners and takeover sweep once; call before takeover."""
    global _registered
    if _registered:
        return
    register_runner(DISCOVERY_JOB_KIND, run_discovery_job)
    register_takeover_sweep("teams scans", fail_interrupted_scans)
    _registered = True


class PeriodicTeamsDiscovery:
    """Queues discovery at start and then every ``interval_seconds``."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self._interval = interval_seconds or settings.teams_discovery_interval_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="teams-discovery")
        logger.info("Teams discovery every %d s", self._interval)

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
                request_discovery()
            except Exception:
                logger.exception("Could not queue Teams discovery")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
