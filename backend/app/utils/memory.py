"""Process memory readings for the processing pipeline.

The backend runs as one container with a hard memory limit, and a pipeline
run allocates and frees hundreds of megabytes. Whether that memory comes back
is invisible from the outside until the task is OOM-killed, so every
processing job logs the resident set size before and after it runs. The
number comes from ``/proc/self/status`` - no dependency, and ``None`` on a
platform without procfs (the dev machines) rather than a wrong value.

When ``MEMORY_DIAGNOSTICS_ENABLED`` is on, ``tracemalloc`` is started at boot
and each job also logs the ten source lines whose Python allocations grew the
most. RSS rising while the Python heap stays flat points at the allocator
(fragmentation, thread arenas); the heap rising points at something in the
process still holding the objects.
"""

import logging
import tracemalloc
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import settings

_PROC_STATUS = "/proc/self/status"
_TOP_LINES = 10


def current_rss_mib() -> float | None:
    """Resident set size of this process in MiB, or ``None`` without procfs."""
    try:
        with open(_PROC_STATUS, encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def log_rss(logger: logging.Logger, stage: str, **fields: object) -> None:
    """Log one ``rss stage=... rss_mib=...`` line with any extra fields."""
    extra = "".join(f" {name}={value}" for name, value in fields.items())
    logger.info("rss stage=%s rss_mib=%s%s", stage, _fmt(current_rss_mib()), extra)


def start_tracemalloc_if_enabled() -> bool:
    """Start tracemalloc when diagnostics are enabled. Returns whether it runs."""
    if not settings.memory_diagnostics_enabled:
        return False
    if not tracemalloc.is_tracing():
        tracemalloc.start(25)
    return True


@asynccontextmanager
async def memory_probe(logger: logging.Logger, label: str) -> AsyncIterator[None]:
    """Log RSS before and after the block, plus tracemalloc growth if enabled.

    The line reads ``pipeline memory: <label> rss_before=... rss_after=...
    delta=...``; grepping ``pipeline memory`` in CloudWatch over consecutive
    jobs shows whether the process is settling or ratcheting.
    """
    tracing = settings.memory_diagnostics_enabled and tracemalloc.is_tracing()
    before_snapshot = tracemalloc.take_snapshot() if tracing else None
    before = current_rss_mib()
    try:
        yield
    finally:
        after = current_rss_mib()
        delta = None if before is None or after is None else after - before
        logger.info(
            "pipeline memory: %s rss_before=%s rss_after=%s delta=%s",
            label,
            _fmt(before),
            _fmt(after),
            "n/a" if delta is None else f"{delta:+.1f}",
        )
        if before_snapshot is not None:
            growth = tracemalloc.take_snapshot().compare_to(before_snapshot, "lineno")
            for stat in growth[:_TOP_LINES]:
                logger.info("pipeline memory growth: %s %s", label, stat)
