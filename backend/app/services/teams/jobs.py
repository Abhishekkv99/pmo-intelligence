"""When Teams chat work runs: discovery at start, daily, and on request; the
review of which chats are watched after discovery, a register edit or a link.

Discovery is a processing-queue job of kind ``teams_discovery`` with one fixed
id, as the recordings scan is: the queue keeps one job per (kind, id), so a
pass never overlaps another, and only the task that owns processing runs it.
The loop and "Scan now" only enqueue. Backlog priority puts session and chat
work first.

A pass cut short by a shutdown leaves its ``teams_scans`` row ``running``; the
next owner's takeover sweep marks it failed.

The watch review (``teams_watch``, one job per chat; ``teams_watch_placement``,
one per placement after a register edit) runs only with ``TEAMS_ENABLED``: it
reads members, so it waits for the Teams rollout even where discovery is on.
After every discovery pass, every chat tied to a placement or watched is
reviewed, so a chat stops being watched the day its placement's end passes.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from app.config import settings
from app.db.repositories.teams_repo import TeamsRepository
from app.db.session import async_session_factory
from app.services.processing_ownership import register_takeover_sweep
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    SESSION_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)
from app.services.teams.discovery import TeamsDiscovery
from app.services.teams.watch import TeamsWatch

logger = logging.getLogger(__name__)

DISCOVERY_JOB_KIND = "teams_discovery"
# Fixed so that every request for discovery is the same job to the queue.
DISCOVERY_JOB_ID = uuid.UUID("7ea50000-0000-4000-8000-00000000d15c")
WATCH_JOB_KIND = "teams_watch"
WATCH_PLACEMENT_JOB_KIND = "teams_watch_placement"

INTERRUPTED_REASON = "Interrupted by a restart before it finished"

# The lifespan registers on every start; a test app starts many times.
_registered = False


def discovery_job() -> Job:
    return Job(kind=DISCOVERY_JOB_KIND, id=DISCOVERY_JOB_ID, priority=BACKLOG_PRIORITY)


def request_discovery() -> bool:
    """Queue discovery; False when a pass is already waiting to start (one asked
    for during a running pass runs after it)."""
    return get_processing_queue().enqueue(discovery_job())


def request_watch(chat_ids: Iterable[uuid.UUID]) -> int:
    """Queue each chat's watch review; how many were queued (none while Teams
    is off). Session priority: a person linking a chat waits for it."""
    if not settings.teams_enabled:
        return 0
    queue = get_processing_queue()
    return sum(
        1
        for chat_id in dict.fromkeys(chat_ids)
        if queue.enqueue(
            Job(kind=WATCH_JOB_KIND, id=chat_id, priority=SESSION_PRIORITY)
        )
    )


def request_placement_watch(placement_ids: Iterable[uuid.UUID]) -> int:
    """Queue the review of each placement's chats (after a register edit)."""
    if not settings.teams_enabled:
        return 0
    queue = get_processing_queue()
    return sum(
        1
        for placement_id in dict.fromkeys(placement_ids)
        if queue.enqueue(
            Job(
                kind=WATCH_PLACEMENT_JOB_KIND,
                id=placement_id,
                priority=SESSION_PRIORITY,
            )
        )
    )


async def run_discovery_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsDiscovery(session).run()
        chat_ids = await TeamsRepository(session).linked_chat_ids()
    queued = request_watch(chat_ids)
    logger.info(
        "Teams watch review after discovery: %d chat(s), %d queued",
        len(chat_ids),
        queued,
    )


async def run_watch_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsWatch(session).review(job.id)


async def run_watch_placement_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsWatch(session).review_placements([job.id])


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
    register_runner(WATCH_JOB_KIND, run_watch_job)
    register_runner(WATCH_PLACEMENT_JOB_KIND, run_watch_placement_job)
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
