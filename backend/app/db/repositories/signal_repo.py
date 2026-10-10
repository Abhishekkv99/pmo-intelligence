"""Queries for signals, issues and actions."""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActionStatus, Dimension, IssueStatus
from app.models.signal import Action, Issue, Signal

# An action still to do; ``overdue`` is set once missed commitments are
# tracked (with Teams chat).
_NOT_DONE = [ActionStatus.OPEN.value, ActionStatus.OVERDUE.value]


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
                Action.status.in_(_NOT_DONE),
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

    async def signals_by_id(
        self, ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, Signal]:
        if not ids:
            return {}
        result = await self.session.execute(select(Signal).where(Signal.id.in_(ids)))
        return {signal.id: signal for signal in result.scalars().all()}

    async def open_issues(self, placement_id: uuid.UUID) -> list[Issue]:
        """The placement's open issues, longest open first."""
        result = await self.session.execute(
            select(Issue)
            .where(
                Issue.placement_id == placement_id,
                Issue.status == IssueStatus.OPEN.value,
            )
            .order_by(Issue.first_seen_at, Issue.id)
        )
        return list(result.scalars().all())

    async def actions_for_placement(self, placement_id: uuid.UUID) -> list[Action]:
        """Every action of the placement: open and overdue first, by due date
        (undated last); then done ones, newest closed first."""
        not_done = Action.status.in_(_NOT_DONE)
        result = await self.session.execute(
            select(Action)
            .where(Action.placement_id == placement_id)
            .order_by(
                case((not_done, 0), else_=1),
                case((not_done, Action.due_date)).asc().nulls_last(),
                Action.closed_at.desc().nulls_last(),
                Action.created_at,
                Action.id,
            )
        )
        return list(result.scalars().all())

    async def next_due_actions(
        self, placement_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, Action]:
        """Each placement's open or overdue action with the earliest due date
        (past dates included); actions without one never count."""
        if not placement_ids:
            return {}
        result = await self.session.execute(
            select(Action)
            .where(
                Action.placement_id.in_(placement_ids),
                Action.status.in_(_NOT_DONE),
                Action.due_date.is_not(None),
            )
            .distinct(Action.placement_id)
            .order_by(
                Action.placement_id, Action.due_date, Action.created_at, Action.id
            )
        )
        return {action.placement_id: action for action in result.scalars().all()}

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

    async def for_placement(
        self, placement_id: uuid.UUID, since: datetime
    ) -> list[Signal]:
        """The placement's signals said at or after ``since``, oldest first."""
        result = await self.session.execute(
            select(Signal)
            .where(Signal.placement_id == placement_id, Signal.occurred_at >= since)
            .order_by(Signal.occurred_at, Signal.offset_ms, Signal.id)
        )
        return list(result.scalars().all())

    async def open_issues_with_technical_signals(
        self, placement_id: uuid.UUID
    ) -> list[tuple[Issue, list[uuid.UUID]]]:
        """The placement's open issues, each with its Technical signals' ids
        (whenever said), for the repeated-blocker trigger."""
        issues = await self.session.execute(
            select(Issue)
            .where(
                Issue.placement_id == placement_id,
                Issue.status == IssueStatus.OPEN.value,
            )
            .order_by(Issue.first_seen_at, Issue.id)
        )
        open_issues = list(issues.scalars().all())
        if not open_issues:
            return []
        signals = await self.session.execute(
            select(Signal.issue_id, Signal.id)
            .where(
                Signal.issue_id.in_([issue.id for issue in open_issues]),
                Signal.dimension == Dimension.TECHNICAL.value,
            )
            .order_by(Signal.occurred_at, Signal.id)
        )
        technical: dict[uuid.UUID, list[uuid.UUID]] = {}
        for issue_id, signal_id in signals.all():
            technical.setdefault(issue_id, []).append(signal_id)
        return [(issue, technical.get(issue.id, [])) for issue in open_issues]

    async def latest_created_at(self) -> dict[uuid.UUID, datetime]:
        """When each placement's newest signal was stored."""
        result = await self.session.execute(
            select(Signal.placement_id, func.max(Signal.created_at)).group_by(
                Signal.placement_id
            )
        )
        return {placement_id: at for placement_id, at in result.all()}

    async def without_embedding(
        self, source_kind: str, source_id: uuid.UUID
    ) -> list[Signal]:
        """The signals of one session or message that have no embedding yet."""
        result = await self.session.execute(
            select(Signal)
            .where(
                Signal.source_kind == source_kind,
                Signal.source_id == source_id,
                Signal.embedding.is_(None),
            )
            .order_by(Signal.occurred_at, Signal.offset_ms, Signal.id)
        )
        return list(result.scalars().all())

    async def sources_without_embedding(self, source_kind: str) -> list[uuid.UUID]:
        """Sessions (or messages) with at least one signal not yet embedded,
        oldest first."""
        result = await self.session.execute(
            select(Signal.source_id)
            .where(Signal.source_kind == source_kind, Signal.embedding.is_(None))
            .group_by(Signal.source_id)
            .order_by(func.min(Signal.occurred_at), Signal.source_id)
        )
        return list(result.scalars().all())

    async def count_without_embedding(self, source_kind: str) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Signal)
            .where(Signal.source_kind == source_kind, Signal.embedding.is_(None))
        )
        return int(result or 0)

    async def closed_by(self, source_id: uuid.UUID) -> list[Action]:
        """Earlier actions that one session or message closed."""
        result = await self.session.execute(
            select(Action)
            .where(Action.closed_source_id == source_id)
            .order_by(Action.created_at, Action.id)
        )
        return list(result.scalars().all())
