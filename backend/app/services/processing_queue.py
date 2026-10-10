"""One process-wide queue that runs processing jobs a few at a time (one, by default).

Every pipeline run - a session recording, a batch of Teams messages, a health
recompute - is enqueued here, and a fixed number of workers
(``PROCESSING_CONCURRENCY``, default 1) run them. That is what bounds the
backend's memory: in the system this was copied from, six parallel batch jobs
each streamed a large copy through the container at once and the task was
OOM-killed; with a bounded queue only a few large allocations are alive at a
time.

The queue is a priority queue with three tiers, FIFO within each. Chat jobs
run first: they are small and many, and they are where "live" comes from.
Session jobs come next: a recording is the richest signal and the slowest.
Bulk backlog work - re-enqueues after a restart, a full recompute - runs
last, so newly arrived evidence never waits for a backlog to drain. A job is
identified by ``(kind, id)`` and is never queued twice while it is pending or
running, so a double click or an overlapping poll cannot queue the same work
again - and the priority is deliberately outside that identity, so a job
cannot sit in the queue twice at two different priorities. A job requested
while the same job is running is remembered and queued once more when it
finishes: what it was asked to look at may have changed after the run read
it (a placement edited during its health recompute), so the request is never
lost, and any number of requests during one run make one more run.

What a job *does* is registered per ``kind`` (``register_runner``) by the
module that owns the pipeline, so this module depends on none of them.

Each job opens its own session: FastAPI closes a request's session before
its background tasks run, so a job can never borrow one. A failing job is
logged and the worker moves on. ``stop()`` cancels the workers without
draining - a transcription takes minutes and ECS allows 30 s - and the
takeover sweeps run by ``processing_ownership`` make the interrupted row
retryable, which is cheaper and safer than writing rows while the engine
shuts down.
"""

import asyncio
import gc
import itertools
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import settings
from app.utils.memory import memory_probe

logger = logging.getLogger(__name__)

# Small, frequent work that keeps the board live (Teams messages).
CHAT_PRIORITY = 0
# A recorded session: rich, slow, less frequent.
SESSION_PRIORITY = 1
# Bulk backlog work, below newly arrived evidence.
BACKLOG_PRIORITY = 2


@dataclass(frozen=True)
class Job:
    """One unit of work: run the ``kind`` pipeline for the row ``id``."""

    kind: str
    id: uuid.UUID
    priority: int = SESSION_PRIORITY
    # Why it was queued, for a runner that records it (a health recompute's
    # snapshot reason); like the priority, not part of the job's identity.
    reason: str | None = None


JobKey = tuple[str, uuid.UUID]
JobRunner = Callable[[Job], Awaitable[None]]


def job_key(job: Job) -> JobKey:
    """The identity a job is deduplicated on: its kind and the row it targets."""
    return (job.kind, job.id)


@dataclass(frozen=True)
class RunningJob:
    job: Job
    started_at: datetime
    worker: int


@dataclass(frozen=True)
class QueueSnapshot:
    """A point-in-time view for the status route and the tests."""

    depth: int
    capacity: int
    running: tuple[RunningJob, ...]
    pending: tuple[Job, ...]


class ProcessingQueue:
    """Priority queue plus N worker tasks; see the module docstring."""

    def __init__(
        self,
        concurrency: int | None = None,
        runner: JobRunner | None = None,
    ) -> None:
        self._capacity = max(1, concurrency or settings.processing_concurrency)
        self._runner: JobRunner = runner or run_job
        self._queue: asyncio.PriorityQueue[tuple[int, int, Job]] = (
            asyncio.PriorityQueue()
        )
        # Tie-breaker so two jobs of one priority dispatch FIFO and the
        # tuple comparison never reaches the (unorderable) job itself.
        self._seq = itertools.count()
        self._pending: dict[JobKey, tuple[int, int, Job]] = {}
        self._running: dict[JobKey, RunningJob] = {}
        # Jobs requested while the same job was running: queued again when
        # it finishes (the latest request's priority and reason).
        self._rerun: dict[JobKey, Job] = {}
        self._workers: list[asyncio.Task[None]] = []
        # Workers that were cancelled by stop() but had not finished within
        # the grace period - a job blocked on I/O that ignores cancellation
        # until it returns. They still occupy their slot and their job.
        self._stragglers: set[asyncio.Task[None]] = set()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def is_running(self) -> bool:
        return bool(self._workers)

    def is_queued(self, job: Job) -> bool:
        """True while the same job (by kind and id) is pending or running."""
        key = job_key(job)
        return key in self._pending or key in self._running

    def enqueue(self, job: Job) -> bool:
        """Queue ``job``; ``False`` if the same job is already pending.

        While the same job is running, it is booked to run once more when it
        finishes (``True``).
        """
        key = job_key(job)
        if key in self._pending:
            logger.info(
                "Job %s %s is already queued; not queued again", job.kind, job.id
            )
            return False
        if key in self._running:
            self._rerun[key] = job
            logger.info(
                "Job %s %s is running; it runs once more when it finishes",
                job.kind,
                job.id,
            )
            return True
        self._put(job)
        return True

    def _put(self, job: Job) -> None:
        key = job_key(job)
        entry = (job.priority, next(self._seq), job)
        self._pending[key] = entry
        self._queue.put_nowait(entry)
        logger.info(
            "Queued %s %s (priority=%d, depth=%d)",
            job.kind,
            job.id,
            job.priority,
            len(self._pending),
        )

    def snapshot(self) -> QueueSnapshot:
        pending = tuple(
            entry[2]
            for entry in sorted(self._pending.values(), key=lambda e: (e[0], e[1]))
        )
        return QueueSnapshot(
            depth=len(self._pending),
            capacity=self._capacity,
            running=tuple(self._running.values()),
            pending=pending,
        )

    async def start(self) -> None:
        """Start the worker tasks. Idempotent."""
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"processing-worker-{index}")
            for index in range(self._capacity)
        ]
        logger.info("Processing queue started (concurrency=%d)", self._capacity)

    # How long stop() waits for cancelled workers to unwind their finally
    # blocks before giving up on them.
    STOP_GRACE_SECONDS: float = 10

    async def stop(self) -> None:
        """Cancel the workers. Pending jobs and re-runs are dropped, never drained."""
        self._rerun.clear()
        workers, self._workers = self._workers, []
        if not workers:
            return
        for worker in workers:
            worker.cancel()
        _done, still_running = await asyncio.wait(
            workers, timeout=self.STOP_GRACE_SECONDS
        )
        if still_running:
            self._stragglers |= still_running
            logger.warning(
                "%d processing worker(s) did not stop within %.0fs",
                len(still_running),
                self.STOP_GRACE_SECONDS,
            )
        logger.info("Processing queue stopped")

    async def wait_for_stragglers(self, log_every: float = 60) -> None:
        """Return once every worker a ``stop()`` cancelled has really ended.

        Starting new workers while old ones are still running would put more
        jobs in flight than ``capacity`` allows - "6 of 3" on 2026-09-24,
        after the database restart froze three jobs mid-write. With the
        database command timeout a frozen job ends within a minute; this
        logs every ``log_every`` seconds while any are left.
        """
        while self._stragglers:
            done, pending = await asyncio.wait(self._stragglers, timeout=log_every)
            self._stragglers -= done
            if pending:
                logger.warning(
                    "Still waiting for %d cancelled processing worker(s) to end",
                    len(pending),
                )

    async def _worker(self, index: int) -> None:
        while True:
            _priority, _seq, job = await self._queue.get()
            key = job_key(job)
            self._pending.pop(key, None)
            self._running[key] = RunningJob(
                job=job, started_at=datetime.now(UTC), worker=index
            )
            logger.info("Running %s %s on worker %d", job.kind, job.id, index)
            try:
                async with memory_probe(logger, f"{job.kind} {job.id}"):
                    await self._runner(job)
            except Exception:
                logger.exception("Processing job %s %s failed", job.kind, job.id)
            finally:
                self._running.pop(key, None)
                again = self._rerun.pop(key, None)
                if again is not None:
                    self._put(again)
                self._queue.task_done()
                # Return what the job freed before the next one allocates.
                gc.collect()


# --- Job execution -----------------------------------------------------------

_runners: dict[str, JobRunner] = {}


def register_runner(kind: str, runner: JobRunner) -> None:
    """Register what a job of ``kind`` does. Called once by the owning module."""
    if kind in _runners and _runners[kind] is not runner:
        raise ValueError(f"A runner for job kind {kind!r} is already registered")
    _runners[kind] = runner


async def run_job(job: Job) -> None:
    """Run one job to completion with the runner registered for its kind."""
    runner = _runners.get(job.kind)
    if runner is None:
        raise LookupError(f"No runner registered for job kind {job.kind!r}")
    await runner(job)


# --- Process-wide instance ---------------------------------------------------

_queue: ProcessingQueue | None = None


def get_processing_queue() -> ProcessingQueue:
    """The process-wide queue, created on first use.

    A module-level instance rather than ``app.state``: pollers and
    schedulers have no request to reach the app through, and unit tests
    build the client without the lifespan and only need a queue that records
    what was enqueued.
    """
    global _queue
    if _queue is None:
        _queue = ProcessingQueue()
    return _queue


def set_processing_queue(queue: ProcessingQueue | None) -> None:
    """Replace the process-wide queue (tests); ``None`` resets to lazy creation."""
    global _queue
    _queue = queue
