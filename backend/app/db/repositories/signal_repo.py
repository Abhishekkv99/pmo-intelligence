"""Queries for signals, issues and actions."""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActionStatus, IssueStatus
from app.models.signal import Action, Issue, Signal


class SignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issues_to_offer(
        self, placement_id: uuid.UUID, resolved_since: datetime
    ) -> list[Issue]:
        """The placement's open issues, and those resolved since a time."""
        result = await self.session.execute(
            select(Issue)
            .where(
                Issue.placement_id == placement_id,
                or_(
                    Issue.status == IssueStatus.OPEN.value,
                    and_(
                        Issue.status == IssueStatus.RESOLVED.value,
                        Issue.resolved_at >= resolved_since,
                    ),
                ),
            )
            .order_by(Issue.first_seen_at, Issue.id)
        )
        return list(result.scalars().all())

    async def open_actions(self, placement_id: uuid.UUID) -> list[Action]:
        """The placement's actions not yet done (open or overdue)."""
        result = await self.session.execute(
            select(Action)
            .where(
                Action.placement_id == placement_id,
                Action.status.in_(
                    [ActionStatus.OPEN.value, ActionStatus.OVERDUE.value]
                ),
            )
            .order_by(Action.created_at, Action.id)
        )
        return list(result.scalars().all())

    async def issues_by_id(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, Issue]:
        if not ids:
            return {}
        result = await self.session.execute(select(Issue).where(Issue.id.in_(ids)))
        return {issue.id: issue for issue in result.scalars().all()}

    async def actions_by_id(
        self, ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, Action]:
        if not ids:
            return {}
        result = await self.session.execute(select(Action).where(Action.id.in_(ids)))
        return {action.id: action for action in result.scalars().all()}

    async def add_all(self, rows: Sequence[Signal | Issue | Action]) -> None:
        self.session.add_all(rows)
        await self.session.flush()

    async def for_source(
        self, source_kind: str, source_id: uuid.UUID
    ) -> tuple[list[Signal], list[Action]]:
        """The signals and actions read from one session or message."""
        signals = await self.session.execute(
            select(Signal)
            .where(Signal.source_kind == source_kind, Signal.source_id == source_id)
            .order_by(Signal.occurred_at, Signal.offset_ms, Signal.id)
        )
        actions = await self.session.execute(
            select(Action)
            .where(Action.source_kind == source_kind, Action.source_id == source_id)
            .order_by(Action.offset_ms, Action.id)
        )
        return list(signals.scalars().all()), list(actions.scalars().all())

    async def closed_by(self, source_id: uuid.UUID) -> list[Action]:
        """Earlier actions that one session or message closed."""
        result = await self.session.execute(
            select(Action)
            .where(Action.closed_source_id == source_id)
            .order_by(Action.created_at, Action.id)
        )
        return list(result.scalars().all())
