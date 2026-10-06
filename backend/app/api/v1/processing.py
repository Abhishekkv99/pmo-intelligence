"""Processing queue observability.

One read-only route reporting the process-wide queue (depth, capacity, the
jobs running now) and the backend's resident memory. It is gated on a global
role rather than scoped to placements: the queue and the process are shared
by every placement, so a scoped view would be wrong, not smaller.
"""

from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies import require_roles
from app.models.enums import Role
from app.schemas.processing_status import ProcessingStatusResponse, RunningJobItem
from app.services.processing_queue import get_processing_queue
from app.utils.memory import current_rss_mib

router = APIRouter()


@router.get(
    "/status",
    response_model=ProcessingStatusResponse,
    dependencies=[Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))],
)
async def get_processing_status() -> ProcessingStatusResponse:
    """A point-in-time view of the processing queue and the backend's memory."""
    snapshot = get_processing_queue().snapshot()
    return ProcessingStatusResponse(
        queue_depth=snapshot.depth,
        capacity=snapshot.capacity,
        running=[
            RunningJobItem(
                kind=entry.job.kind,
                id=entry.job.id,
                started_at=entry.started_at,
                worker=entry.worker,
            )
            for entry in snapshot.running
        ],
        rss_mib=current_rss_mib(),
        memory_diagnostics_enabled=settings.memory_diagnostics_enabled,
    )
