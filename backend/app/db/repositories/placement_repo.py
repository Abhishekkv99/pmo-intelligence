import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.repositories.base import BaseRepository
from app.models.enums import PlacementStatus
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User
from app.utils.entitlements import ListScope


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
    # The consultant's CDM.
    cdm: User | None


class PlacementRepository(BaseRepository[Placement]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Placement)

    async def list_rows(self) -> list[PlacementRow]:
        """Every placement, newest start first."""
        return await self._rows()

    async def get_row(self, placement_id: uuid.UUID) -> PlacementRow | None:
        rows = await self._rows(placement_id=placement_id)
        return rows[0] if rows else None

    async def active_rows(self, scope: ListScope) -> list[PlacementRow]:
        """The active placements ``scope`` may see, newest start first."""
        return await self._rows(scope=scope, active_only=True)

    async def rows_for_consultant(
        self, consultant_id: uuid.UUID, scope: ListScope
    ) -> list[PlacementRow]:
        """The consultant's placements ``scope`` may see, newest start first."""
        return await self._rows(scope=scope, consultant_id=consultant_id)

    async def _rows(
        self,
        *,
        placement_id: uuid.UUID | None = None,
        scope: ListScope | None = None,
        active_only: bool = False,
        consultant_id: uuid.UUID | None = None,
    ) -> list[PlacementRow]:
        if scope is not None and scope.nothing:
            return []
        ps = aliased(User)
        sme = aliased(User)
        cdm = aliased(User)
        stmt = (
            select(Placement, Consultant, Project, Client, ps, sme, cdm)
            .join(Consultant, Consultant.id == Placement.consultant_id)
            .join(Project, Project.id == Placement.project_id)
            .join(Client, Client.id == Project.client_id)
            .outerjoin(ps, ps.id == Placement.ps_user_id)
            .outerjoin(sme, sme.id == Placement.sme_user_id)
            .outerjoin(cdm, cdm.id == Consultant.cdm_user_id)
            .order_by(Placement.start_date.desc(), Consultant.full_name)
        )
        if placement_id is not None:
            stmt = stmt.where(Placement.id == placement_id)
        if consultant_id is not None:
            stmt = stmt.where(Placement.consultant_id == consultant_id)
        if active_only:
            stmt = stmt.where(Placement.status == PlacementStatus.ACTIVE.value)
        if scope is not None and not scope.everything:
            user_id = scope.named_user_id
            stmt = stmt.where(
                or_(
                    Placement.ps_user_id == user_id,
                    Placement.sme_user_id == user_id,
                    Consultant.cdm_user_id == user_id,
                )
            )
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

    async def active_ids(self) -> list[uuid.UUID]:
        """Every active placement's id, oldest start first."""
        result = await self.session.execute(
            select(Placement.id)
            .where(Placement.status == PlacementStatus.ACTIVE.value)
            .order_by(Placement.start_date, Placement.id)
        )
        return list(result.scalars().all())

    async def active_ids_for_project(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(Placement.id)
            .where(
                Placement.project_id == project_id,
                Placement.status == PlacementStatus.ACTIVE.value,
            )
            .order_by(Placement.start_date, Placement.id)
        )
        return list(result.scalars().all())

    async def register_edits(self) -> list[tuple[uuid.UUID, str, datetime]]:
        """Every placement with its status and when it or its project was
        last written, oldest start first."""
        result = await self.session.execute(
            select(
                Placement.id,
                Placement.status,
                func.greatest(Placement.updated_at, Project.updated_at),
            )
            .join(Project, Project.id == Placement.project_id)
            .order_by(Placement.start_date, Placement.id)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def list_for_consultant(self, consultant_id: uuid.UUID) -> list[Placement]:
        """Every placement of a consultant, newest start first."""
        stmt = (
            select(Placement)
            .where(Placement.consultant_id == consultant_id)
            .order_by(Placement.start_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_consultant_client_start(
        self, consultant_id: uuid.UUID, client_id: uuid.UUID, start_date: date
    ) -> list[Placement]:
        """The consultant's placements at this client from this date, on any
        of its projects (the quick add's key, so renaming a project keeps it)."""
        stmt = (
            select(Placement)
            .join(Project, Project.id == Placement.project_id)
            .where(
                Placement.consultant_id == consultant_id,
                Project.client_id == client_id,
                Placement.start_date == start_date,
            )
            .order_by(Placement.created_at, Placement.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
