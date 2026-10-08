import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.repositories.base import BaseRepository
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User


@dataclass(frozen=True)
class PlacementRow:
    """A placement with everything the register table shows beside it.

    Loaded in one joined query: the related rows are not relationships, and a
    lazy load would raise MissingGreenlet under async.
    """

    placement: Placement
    consultant: Consultant
    project: Project
    client: Client
    ps: User | None
    sme: User | None
    tech_lead: User | None


class PlacementRepository(BaseRepository[Placement]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Placement)

    async def list_rows(self) -> list[PlacementRow]:
        """Every placement, newest start first."""
        return await self._rows(None)

    async def get_row(self, placement_id: uuid.UUID) -> PlacementRow | None:
        rows = await self._rows(placement_id)
        return rows[0] if rows else None

    async def _rows(self, placement_id: uuid.UUID | None) -> list[PlacementRow]:
        ps = aliased(User)
        sme = aliased(User)
        tech_lead = aliased(User)
        stmt = (
            select(Placement, Consultant, Project, Client, ps, sme, tech_lead)
            .join(Consultant, Consultant.id == Placement.consultant_id)
            .join(Project, Project.id == Placement.project_id)
            .join(Client, Client.id == Project.client_id)
            .outerjoin(ps, ps.id == Placement.ps_user_id)
            .outerjoin(sme, sme.id == Placement.sme_user_id)
            .outerjoin(tech_lead, tech_lead.id == Project.tech_lead_user_id)
            .order_by(Placement.start_date.desc(), Consultant.full_name)
        )
        if placement_id is not None:
            stmt = stmt.where(Placement.id == placement_id)
        result = await self.session.execute(stmt)
        return [PlacementRow(*row) for row in result.all()]

    async def get_by_key(
        self, consultant_id: uuid.UUID, project_id: uuid.UUID, start_date: date
    ) -> Placement | None:
        """The placement of this consultant on this project from this date."""
        stmt = select(Placement).where(
            Placement.consultant_id == consultant_id,
            Placement.project_id == project_id,
            Placement.start_date == start_date,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
