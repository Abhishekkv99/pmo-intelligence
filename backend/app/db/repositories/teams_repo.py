"""Queries for the Teams group chats and their discovery passes."""

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    HistoryState,
    Role,
    ScanStatus,
    SpeakerRole,
    TeamsChatMatch,
    TeamsWatchState,
)
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import GraphSubscription, Message, TeamsGroup, TeamsScan
from app.models.user import User
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

    # --- Messages, syncs and subscriptions (Sprint 4 Phase 5) ---------------

    async def watching_chat_ids(self) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(TeamsGroup.id).where(
                TeamsGroup.watch_state == TeamsWatchState.WATCHING.value
            )
        )
        return list(result.scalars())

    async def subscribed_or_watching_chat_ids(self) -> list[uuid.UUID]:
        """Chats watched, and chats that still have a subscription to remove."""
        result = await self.session.execute(
            select(TeamsGroup.id)
            .outerjoin(
                GraphSubscription, GraphSubscription.teams_group_id == TeamsGroup.id
            )
            .where(
                (TeamsGroup.watch_state == TeamsWatchState.WATCHING.value)
                | GraphSubscription.id.is_not(None)
            )
        )
        return list(result.scalars())

    async def chats_needing_sync(self) -> list[uuid.UUID]:
        """Watched chats whose history is unread, or that were asked to sync
        after their last sync started."""
        result = await self.session.execute(
            select(TeamsGroup.id).where(
                TeamsGroup.watch_state == TeamsWatchState.WATCHING.value,
                (TeamsGroup.history_state == HistoryState.NONE.value)
                | (
                    TeamsGroup.sync_requested_at.is_not(None)
                    & (
                        TeamsGroup.last_synced_at.is_(None)
                        | (TeamsGroup.sync_requested_at > TeamsGroup.last_synced_at)
                    )
                ),
            )
        )
        return list(result.scalars())

    async def messages_by_graph_id(
        self, chat_id: uuid.UUID, graph_ids: list[str]
    ) -> dict[str, Message]:
        if not graph_ids:
            return {}
        result = await self.session.execute(
            select(Message).where(
                Message.teams_group_id == chat_id,
                Message.graph_message_id.in_(graph_ids),
            )
        )
        return {m.graph_message_id: m for m in result.scalars()}

    async def latest_modified_at(self, chat_id: uuid.UUID) -> datetime | None:
        """The newest change stored for the chat: the next sync reads after it."""
        latest: datetime | None = await self.session.scalar(
            select(func.max(Message.last_modified_at)).where(
                Message.teams_group_id == chat_id
            )
        )
        return latest

    async def latest_post_at(self, chat_id: uuid.UUID) -> datetime | None:
        """When the newest message (not a system event, not deleted) was posted."""
        latest: datetime | None = await self.session.scalar(
            select(func.max(Message.posted_at)).where(
                Message.teams_group_id == chat_id,
                Message.message_type == "message",
                Message.deleted_at.is_(None),
            )
        )
        return latest

    async def author_roles(self, placement: Placement | None) -> dict[str, SpeakerRole]:
        """Entra id to role for the people of the chat's placement and the PMO."""
        roles: dict[str, SpeakerRole] = {}
        managers = await self.session.execute(
            select(User.entra_oid).where(
                User.role == Role.PMO_MANAGER.value, User.entra_oid.is_not(None)
            )
        )
        for (oid,) in managers.all():
            roles[str(oid)] = SpeakerRole.PMO_MANAGER
        if placement is None:
            return roles
        cdm_user_id = await self.session.scalar(
            select(Consultant.cdm_user_id).where(
                Consultant.id == placement.consultant_id
            )
        )
        people = (
            (placement.ps_user_id, SpeakerRole.PS),
            (placement.sme_user_id, SpeakerRole.SME),
            (cdm_user_id, SpeakerRole.CDM),
        )
        for user_id, role in people:
            if user_id is None:
                continue
            oid = await self.session.scalar(
                select(User.entra_oid).where(User.id == user_id)
            )
            if oid:
                roles[str(oid)] = role
        return roles

    async def subscription_for_chat(
        self, chat_id: uuid.UUID
    ) -> GraphSubscription | None:
        sub: GraphSubscription | None = await self.session.scalar(
            select(GraphSubscription).where(GraphSubscription.teams_group_id == chat_id)
        )
        return sub

    async def subscriptions_by_id(
        self, subscription_ids: list[str]
    ) -> dict[str, tuple[GraphSubscription, TeamsGroup]]:
        """The known subscriptions among ``subscription_ids``, with their chats."""
        if not subscription_ids:
            return {}
        result = await self.session.execute(
            select(GraphSubscription, TeamsGroup)
            .join(TeamsGroup, TeamsGroup.id == GraphSubscription.teams_group_id)
            .where(GraphSubscription.subscription_id.in_(subscription_ids))
        )
        return {sub.subscription_id: (sub, chat) for sub, chat in result.tuples()}

    async def request_sync(self, chat_ids: list[uuid.UUID], at: datetime) -> None:
        if chat_ids:
            await self.session.execute(
                update(TeamsGroup)
                .where(TeamsGroup.id.in_(chat_ids))
                .values(sync_requested_at=at)
            )

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
