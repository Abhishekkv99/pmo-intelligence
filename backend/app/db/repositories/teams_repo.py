"""Queries for the Teams group chats and their discovery passes."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ScanStatus
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup, TeamsScan
from app.services.teams.chat_match import PlacementCandidate


class TeamsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def chats_by_graph_id(self) -> dict[str, TeamsGroup]:
        result = await self.session.execute(select(TeamsGroup))
        return {chat.graph_chat_id: chat for chat in result.scalars()}

    async def placement_candidates(self) -> list[PlacementCandidate]:
        """Every placement with its consultant's and client's names, for matching."""
        result = await self.session.execute(
            select(
                Placement.id,
                Placement.consultant_id,
                Consultant.full_name,
                Client.name,
                Placement.start_date,
            )
            .join(Consultant, Placement.consultant_id == Consultant.id)
            .join(Project, Placement.project_id == Project.id)
            .join(Client, Project.client_id == Client.id)
        )
        return [PlacementCandidate(*row) for row in result.all()]

    def add(self, row: TeamsGroup) -> None:
        self.session.add(row)

    async def flush(self) -> None:
        await self.session.flush()

    async def start_scan(self, started_at: datetime) -> TeamsScan:
        scan = TeamsScan(started_at=started_at, status=ScanStatus.RUNNING.value)
        self.session.add(scan)
        await self.session.flush()
        return scan

    async def finish_scan(
        self,
        scan_id: uuid.UUID,
        *,
        finished_at: datetime,
        status: ScanStatus,
        error_message: str | None = None,
        **counts: int,
    ) -> None:
        await self.session.execute(
            update(TeamsScan)
            .where(TeamsScan.id == scan_id)
            .values(
                finished_at=finished_at,
                status=status.value,
                error_message=error_message,
                **counts,
            )
        )

    async def latest_scan(self) -> TeamsScan | None:
        result = await self.session.execute(
            select(TeamsScan).order_by(TeamsScan.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def fail_running_scans(self, finished_at: datetime, reason: str) -> int:
        """Mark every pass still ``running`` as failed; returns how many."""
        result = await self.session.execute(
            update(TeamsScan)
            .where(TeamsScan.status == ScanStatus.RUNNING.value)
            .values(
                status=ScanStatus.FAILED.value,
                finished_at=finished_at,
                error_message=reason,
            )
            .returning(TeamsScan.id)
        )
        return len(result.all())
