"""Response schema for ``GET /processing/status``."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RunningJobItem(BaseModel):
    """A job a worker is executing right now."""

    kind: str = Field(description="The pipeline the job runs")
    id: uuid.UUID = Field(description="The row the job targets")
    started_at: datetime
    worker: int = Field(description="Zero-based index of the worker running it")


class ProcessingStatusResponse(BaseModel):
    queue_depth: int = Field(description="Jobs waiting to run")
    capacity: int = Field(description="Worker count (PROCESSING_CONCURRENCY)")
    running: list[RunningJobItem]
    rss_mib: float | None = Field(
        description="Resident set size of the backend process in MiB; null where "
        "/proc/self/status is unavailable"
    )
    memory_diagnostics_enabled: bool
