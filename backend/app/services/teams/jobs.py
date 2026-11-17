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

Reading messages (Sprint 4 Phase 5), also only with ``TEAMS_ENABLED``:

- ``teams_subscription`` (one per chat, session priority) makes, renews or
  deletes the chat's Graph subscription (``subscriptions``); it runs after
  every watch review, on a lifecycle event, and every
  ``TEAMS_SUBSCRIPTION_CHECK_SECONDS`` for every watched or subscribed chat.
  A subscription just made queues a sync.
- ``teams_sync`` (one per chat, chat priority) reads the history or the
  changes (``messages``). Asked for by a notification, a lifecycle ``missed``
  event, a new subscription, and the daily catch-up, never on a timer of its
  own; each request records ``sync_requested_at`` so a takeover can queue it
  again.
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
from app.services.processing_ownership import (
    register_takeover_requeue,
    register_takeover_sweep,
)
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    CHAT_PRIORITY,
    SESSION_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)
from app.services.teams.discovery import TeamsDiscovery
from app.services.teams.messages import TeamsSync
from app.services.teams.subscriptions import Ask, Outcome, TeamsSubscriptions
from app.services.teams.watch import TeamsWatch

logger = logging.getLogger(__name__)

DISCOVERY_JOB_KIND = "teams_discovery"
# Fixed so that every request for discovery is the same job to the queue.
DISCOVERY_JOB_ID = uuid.UUID("7ea50000-0000-4000-8000-00000000d15c")
WATCH_JOB_KIND = "teams_watch"
WATCH_PLACEMENT_JOB_KIND = "teams_watch_placement"
SYNC_JOB_KIND = "teams_sync"
SUBSCRIPTION_JOB_KIND = "teams_subscription"
# The catch-up reads every watched chat once a day: Microsoft's polling limit.
CATCH_UP_SECONDS = 86_400

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


def request_sync(chat_ids: Iterable[uuid.UUID]) -> int:
    """Queue each chat's sync; how many were queued (none while Teams is off).
    The caller records ``sync_requested_at``."""
    if not settings.teams_enabled:
        return 0
    queue = get_processing_queue()
    return sum(
        1
        for chat_id in dict.fromkeys(chat_ids)
        if queue.enqueue(Job(kind=SYNC_JOB_KIND, id=chat_id, priority=CHAT_PRIORITY))
    )


def request_subscription_review(
    chat_ids: Iterable[uuid.UUID], ask: Ask | None = None
) -> int:
    """Queue each chat's subscription review (none while Teams is off)."""
    if not settings.teams_enabled:
        return 0
    queue = get_processing_queue()
    return sum(
        1
        for chat_id in dict.fromkeys(chat_ids)
        if queue.enqueue(
            Job(
                kind=SUBSCRIPTION_JOB_KIND,
                id=chat_id,
                priority=SESSION_PRIORITY,
                reason=ask.value if ask is not None else None,
            )
        )
    )


async def record_and_request_sync(chat_ids: list[uuid.UUID]) -> int:
    """Record that each chat was asked to sync, then queue the syncs."""
    if not settings.teams_enabled or not chat_ids:
        return 0
    async with async_session_factory() as session:
        await TeamsRepository(session).request_sync(chat_ids, datetime.now(UTC))
        await session.commit()
    return request_sync(chat_ids)


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
    request_subscription_review([job.id])


async def run_watch_placement_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsWatch(session).review_placements([job.id])
        chat_ids = await TeamsRepository(session).chat_ids_for_placements([job.id])
    request_subscription_review(chat_ids)


async def run_subscription_job(job: Job) -> None:
    ask = Ask(job.reason) if job.reason in set(Ask) else None
    async with async_session_factory() as session:
        outcome = await TeamsSubscriptions(session).review(job.id, ask)
    if outcome == Outcome.CREATED:
        # The history the first time; afterwards what changed meanwhile.
        await record_and_request_sync([job.id])


async def run_sync_job(job: Job) -> None:
    async with async_session_factory() as session:
        await TeamsSync(session).sync(job.id)


async def requeue_requested_syncs() -> int:
    """Takeover: queue the watched chats asked to sync since their last sync
    (a notification the previous owner never ran) or whose history is unread."""
    if not settings.teams_enabled:
        return 0
    async with async_session_factory() as session:
        chat_ids = await TeamsRepository(session).chats_needing_sync()
    request_sync(chat_ids)
    return len(chat_ids)


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
    register_runner(SUBSCRIPTION_JOB_KIND, run_subscription_job)
    register_runner(SYNC_JOB_KIND, run_sync_job)
    register_takeover_sweep("teams scans", fail_interrupted_scans)
    register_takeover_requeue("teams syncs", requeue_requested_syncs)
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


class PeriodicTeamsUpkeep:
    """While Teams is on: at start and every ``interval_seconds``, queues the
    subscription review of every watched or subscribed chat (renewals); at
    start and then once a day, records and queues the catch-up sync of every
    watched chat (one date-ranged read each)."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        catch_up_seconds: int = CATCH_UP_SECONDS,
    ) -> None:
        self._interval = interval_seconds or settings.teams_subscription_check_seconds
        self._catch_up = catch_up_seconds
        self._last_catch_up: float | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="teams-upkeep")
        logger.info(
            "Teams subscriptions checked every %d s; catch-up every %d s",
            self._interval,
            self._catch_up,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def tick(self, now: float) -> None:
        async with async_session_factory() as session:
            teams = TeamsRepository(session)
            subscribed = await teams.subscribed_or_watching_chat_ids()
            watching = await teams.watching_chat_ids()
        request_subscription_review(subscribed)
        if self._last_catch_up is None or now - self._last_catch_up >= self._catch_up:
            self._last_catch_up = now
            queued = await record_and_request_sync(watching)
            logger.info(
                "Teams catch-up: %d watched chat(s), %d queued", len(watching), queued
            )

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                await self.tick(loop.time())
            except Exception:
                logger.exception("Teams upkeep failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
