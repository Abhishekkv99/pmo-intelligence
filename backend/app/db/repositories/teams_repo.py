"""Queries for the Teams group chats and their discovery passes."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ScanStatus, TeamsChatMatch, TeamsWatchState
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup, TeamsScan
from app.schemas.teams import TeamsPlacement
from app.services.teams.chat_match import PlacementCandidate

logger = logging.getLogger(__name__)

LINKED = (TeamsChatMatch.MATCHED.value, TeamsChatMatch.CHOSEN.value)


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

    async def get_chat(self, chat_id: uuid.UUID) -> TeamsGroup | None:
        return await self.session.get(TeamsGroup, chat_id)

    async def chat_with_placement(
        self, chat_id: uuid.UUID
    ) -> tuple[TeamsGroup, Placement | None, Consultant | None] | None:
        """A chat with its placement and the placement's consultant, if linked."""
        result = await self.session.execute(
            select(TeamsGroup, Placement, Consultant)
            .outerjoin(Placement, TeamsGroup.placement_id == Placement.id)
            .outerjoin(Consultant, Placement.consultant_id == Consultant.id)
            .where(TeamsGroup.id == chat_id)
        )
        row = result.one_or_none()
        return None if row is None else (row[0], row[1], row[2])

    async def linked_chat_ids(self) -> list[uuid.UUID]:
        """Chats tied to a placement (matched or chosen), and chats watched."""
        result = await self.session.execute(
            select(TeamsGroup.id).where(
                TeamsGroup.match_status.in_(LINKED)
                | (TeamsGroup.watch_state == TeamsWatchState.WATCHING.value)
            )
        )
        return list(result.scalars())

    async def chat_ids_for_placements(
        self, placement_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        if not placement_ids:
            return []
        result = await self.session.execute(
            select(TeamsGroup.id).where(TeamsGroup.placement_id.in_(placement_ids))
        )
        return list(result.scalars())

    async def link_consultant_oid(self, consultant: Consultant, oid: str) -> None:
        """Record a consultant's Entra id unless they have one or another holds it."""
        if consultant.entra_oid:
            return
        holder = await self.session.scalar(
            select(Consultant.id).where(
                Consultant.entra_oid == oid, Consultant.id != consultant.id
            )
        )
        if holder is not None:
            logger.warning(
                "Entra id of consultant %s not recorded: consultant %s holds it",
                consultant.id,
                holder,
            )
            return
        consultant.entra_oid = oid

    async def list_chats(self) -> list[TeamsGroup]:
        """Every PMO chat, by title (then id, for titles typed twice)."""
        result = await self.session.execute(
            select(TeamsGroup).order_by(TeamsGroup.title, TeamsGroup.id)
        )
        return list(result.scalars().all())

    async def placement_summaries(
        self, placement_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, TeamsPlacement]:
        """The placements by id, with their consultant, client and project names."""
        if not placement_ids:
            return {}
        result = await self.session.execute(
            select(Placement, Consultant.full_name, Client.name, Project.name)
            .join(Consultant, Placement.consultant_id == Consultant.id)
            .join(Project, Placement.project_id == Project.id)
            .join(Client, Project.client_id == Client.id)
            .where(Placement.id.in_(placement_ids))
        )
        return {
            placement.id: TeamsPlacement(
                id=placement.id,
                consultant_name=consultant,
                client_name=client,
                project_name=project,
                start_date=placement.start_date,
                expected_end_date=placement.expected_end_date,
                status=placement.status,
            )
            for placement, consultant, client, project in result.all()
        }

    async def placement_exists(self, placement_id: uuid.UUID) -> bool:
        return await self.session.get(Placement, placement_id) is not None

    async def placement_consultant(self, placement_id: uuid.UUID) -> Consultant | None:
        result = await self.session.execute(
            select(Consultant)
            .join(Placement, Placement.consultant_id == Consultant.id)
            .where(Placement.id == placement_id)
        )
        return result.scalar_one_or_none()

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
