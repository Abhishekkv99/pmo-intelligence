"""Exactly one backend task owns processing at a time.

An ECS rolling deploy starts the new backend task, waits for it to be
healthy, marks the old one to stop and drains its load-balancer connections
for the target group's deregistration delay (60 s, ``alb.tf``; AWS's default
of 300 s held processing back about 6 minutes per deploy) before the old task
is signalled. For that time both tasks are alive. Without ownership each
runs its own queue over the same backlog, and the new task's startup sweep
fails every row still mid-processing - including rows the old task is
actively working on and would finish a minute later. Worse, the old task
keeps starting jobs after that sweep, and the ones it has not finished when
it is stopped are left mid-state with no sweep ever to come for them (this
happened in the system this module was copied from).

The fix is ownership. A task takes a Postgres session-level advisory lock on
a dedicated connection before it starts its workers, runs its sweeps, or
re-queues the backlog, and holds it for as long as its queue runs. The new
task therefore waits for the old one to stop, and its sweep sees exactly
what the old task left behind. The lock lives and dies with the connection:
a clean shutdown stops the queue and then closes it, and a killed process's
socket closes with it, so Postgres releases the lock either way.

The wait happens in a background task, not in the lifespan: uvicorn serves
no request until startup finishes, and the container health check would
kill a task that spent six minutes starting. While it waits the task serves
requests normally and anything they enqueue simply waits in the queue.

The lock can also be lost while the task lives. It dies with its
connection, and a database blip that drops that one connection releases it
without the task noticing - in the system this was copied from, a blip
did exactly that, and at the next deploy the new task took ownership after
0 s and swept five rows the old task was still running. So the owner checks
the lock
every ``HEARTBEAT_SECONDS`` (``hold_processing``): if it is gone the task
stops its queue at once, logs an ERROR, and goes back to waiting for the
lock like a newly started task.

What a takeover recovers is registered by the modules that own the rows
(``register_takeover_sweep``, ``register_takeover_requeue``), so this module
depends on none of them.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.services.processing_queue import ProcessingQueue

logger = logging.getLogger(__name__)

# A recovery step run on takeover: returns how many rows it touched.
TakeoverStep = Callable[[], Awaitable[int]]

# Sweeps run before the queue starts: they make rows the previous owner left
# mid-processing retryable. Re-queues run after it starts: they put the
# pending backlog back on the queue. Each is (name, step), run in order.
_takeover_sweeps: list[tuple[str, TakeoverStep]] = []
_takeover_requeues: list[tuple[str, TakeoverStep]] = []


def register_takeover_sweep(name: str, step: TakeoverStep) -> None:
    """Run ``step`` on every takeover, before the queue starts."""
    _takeover_sweeps.append((name, step))


def register_takeover_requeue(name: str, step: TakeoverStep) -> None:
    """Run ``step`` on every takeover, after the queue starts."""
    _takeover_requeues.append((name, step))


# An arbitrary fixed 64-bit value that nothing else in the database uses as
# an advisory lock key. Written out as a literal so it can never change
# between two deployed versions - the old and new task must agree on it.
PROCESSING_LOCK_KEY = 0x2C4F_1A6B_83D0_5E17

# How long to wait before trying again when taking the lock raised (as
# opposed to finding it held, which polls every ``poll_seconds``).
ACQUIRE_RETRY_SECONDS = 15.0

# How often the owner confirms it still holds the lock. Bounds how long a
# task can go on processing after silently losing it.
HEARTBEAT_SECONDS = 30.0

# True when this connection's backend holds the advisory lock ``key``. A
# bigint advisory key is stored split across classid (high 32 bits) and
# objid (low 32 bits), with objsubid 1.
_HOLDS_LOCK_SQL = text(
    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
    "AND pid = pg_backend_pid() AND granted AND objsubid = 1 "
    "AND ((classid::bigint << 32) | objid::bigint) = :key)"
)


class ProcessingOwnership:
    """A Postgres advisory lock held for as long as this process processes."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        key: int = PROCESSING_LOCK_KEY,
        poll_seconds: float = 5.0,
    ) -> None:
        self._engine = engine
        self._key = key
        self._poll_seconds = poll_seconds
        self._connection: AsyncConnection | None = None

    @property
    def is_held(self) -> bool:
        return self._connection is not None

    async def acquire(self) -> None:
        """Wait until the lock is held. Polls; never blocks a DB session."""
        if self._connection is not None:
            return
        # Autocommit, so holding the connection open never leaves a
        # transaction idle for the minutes (or days) the lock is held.
        connection = await self._engine.connect()
        try:
            connection = await connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            started = time.monotonic()
            waiting_logged = False
            while True:
                result = await connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}
                )
                if result.scalar_one():
                    break
                if not waiting_logged:
                    logger.info(
                        "Waiting for processing ownership: another backend task "
                        "holds it (normal during a deploy)"
                    )
                    waiting_logged = True
                await asyncio.sleep(self._poll_seconds)
        except BaseException:
            await connection.close()
            raise
        self._connection = connection
        logger.info("Took processing ownership after %.0fs", time.monotonic() - started)

    async def still_held(self) -> bool:
        """Confirm the lock is still held on its connection.

        ``False`` - after logging why - when the connection has failed or the
        lock is no longer in ``pg_locks``; the dead connection is then
        dropped, so ``is_held`` is false and ``acquire()`` starts afresh.
        """
        connection = self._connection
        if connection is None:
            return False
        try:
            result = await connection.execute(_HOLDS_LOCK_SQL, {"key": self._key})
            if result.scalar_one():
                return True
            logger.error("Processing lock is no longer held by this task")
        except Exception:
            logger.error("Processing lock connection failed", exc_info=True)
        self._connection = None
        with contextlib.suppress(Exception):
            await connection.close()
        return False

    async def release(self) -> None:
        """Give the lock up. Closing the connection releases it. Idempotent."""
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": self._key}
            )
        finally:
            await connection.close()
        # Without this line a clean release cannot be told from a dropped
        # connection when reading a deploy's logs.
        logger.info("Released processing ownership")


async def take_over_processing(
    ownership: ProcessingOwnership, queue: ProcessingQueue
) -> None:
    """Wait for ownership, recover what the previous owner left, then process.

    Order matters. The sweeps run only once the previous task's queue has
    stopped, so a row they fail really was abandoned, and before this queue
    starts, so a recovered row cannot race a new job. The re-queues run after
    ``start()``. Every step but the lock is non-fatal: a failed sweep or
    re-queue leaves rows retryable by hand, never a task that processes
    nothing.
    """
    # Keep trying: a database that is briefly unreachable at boot must not
    # leave a task that serves requests but never processes anything.
    while True:
        try:
            await ownership.acquire()
            break
        except Exception:
            logger.warning(
                "Could not take processing ownership; retrying in %.0fs",
                ACQUIRE_RETRY_SECONDS,
                exc_info=True,
            )
            await asyncio.sleep(ACQUIRE_RETRY_SECONDS)

    await _run_steps("sweep", _takeover_sweeps)
    await queue.start()
    await _run_steps("re-queue", _takeover_requeues)


async def _run_steps(label: str, steps: list[tuple[str, TakeoverStep]]) -> None:
    for name, step in steps:
        try:
            count = await step()
            # Logged even at zero, so "ran and found nothing" can be told
            # from "never ran".
            logger.info("Takeover %s %s: %d row(s)", label, name, count)
        except Exception:
            logger.warning(
                "Takeover %s %s failed (non-fatal)", label, name, exc_info=True
            )


async def hold_processing(
    ownership: ProcessingOwnership,
    queue: ProcessingQueue,
    *,
    heartbeat_seconds: float | None = None,
) -> None:
    """Own processing for as long as this process lives.

    Takes over (``take_over_processing``), then checks the lock every
    ``heartbeat_seconds``. When it is lost the queue is stopped at once -
    running jobs are cancelled and no new one starts, so at most one
    heartbeat of unowned processing can overlap another owner. A cancelled
    job blocked on I/O can outlive the stop, so the task first waits for
    every old worker to end (``wait_for_stragglers``), then goes back to
    waiting for the lock. On taking it back the usual
    takeover runs: the sweep makes the jobs it just cancelled retryable,
    the workers start and the backlog is re-queued. Runs until cancelled.
    """
    while True:
        await take_over_processing(ownership, queue)
        interval = HEARTBEAT_SECONDS if heartbeat_seconds is None else heartbeat_seconds
        while True:
            await asyncio.sleep(interval)
            if not await ownership.still_held():
                break
        logger.error(
            "Lost processing ownership; stopped the processing queue and "
            "waiting to take it back"
        )
        await queue.stop()
        # Only take over again once the old workers have really ended, or the
        # new ones would run alongside them.
        await queue.wait_for_stragglers()
