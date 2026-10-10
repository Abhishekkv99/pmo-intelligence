"""The risk board and a placement's health page.

The board lists the active placements in the caller's scope and is not
logged; the placement page shows a consultant's data, so it is read through
the logged placement-scope guard (404 outside scope, an ``access_log`` row
for every read). An SME sees the technical view of both.
"""

from fastapi import APIRouter, Depends

from app.dependencies import (
    DbSession,
    LoggedPlacementScope,
    get_current_user,
    require_roles,
)
from app.models.enums import Role
from app.models.user import User
from app.schemas.health import PlacementHealth, RiskBoardRow
from app.services.health_view import HealthViewService

router = APIRouter()

# Any role may read the board; it is cut to the caller's scope.
ANY_ROLE = require_roles(*Role)


@router.get("/risk-board", response_model=list[RiskBoardRow])
async def risk_board(
    db: DbSession, current_user: User = Depends(ANY_ROLE)
) -> list[RiskBoardRow]:
    """Every active placement in the caller's scope, red first."""
    return await HealthViewService(db).risk_board(current_user)


@router.get("/placements/{placement_id}/health", response_model=PlacementHealth)
async def placement_health(
    placement: LoggedPlacementScope,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> PlacementHealth:
    """The placement page: scores, evidence, history, flags, calls, actions."""
    return await HealthViewService(db).placement_health(placement, current_user)
