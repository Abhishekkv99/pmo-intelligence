"""Queries for health snapshots and risk flags."""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import HealthSnapshot, RiskFlag


class HealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_snapshot(self, snapshot: HealthSnapshot) -> HealthSnapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def latest_snapshot(self, placement_id: uuid.UUID) -> HealthSnapshot | None:
        result = await self.session.execute(
            select(HealthSnapshot)
            .where(HealthSnapshot.placement_id == placement_id)
            .order_by(HealthSnapshot.computed_at.desc(), HealthSnapshot.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_snapshots(
        self, placement_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, HealthSnapshot]:
        """The newest snapshot of each placement that has one."""
        if not placement_ids:
            return {}
        result = await self.session.execute(
            select(HealthSnapshot)
            .where(HealthSnapshot.placement_id.in_(placement_ids))
            .distinct(HealthSnapshot.placement_id)
            .order_by(
                HealthSnapshot.placement_id,
                HealthSnapshot.computed_at.desc(),
                HealthSnapshot.id.desc(),
            )
        )
        return {s.placement_id: s for s in result.scalars().all()}

    async def history(self, placement_id: uuid.UUID) -> list[HealthSnapshot]:
        """Every snapshot of the placement, oldest first."""
        result = await self.session.execute(
            select(HealthSnapshot)
            .where(HealthSnapshot.placement_id == placement_id)
            .order_by(HealthSnapshot.computed_at, HealthSnapshot.id)
        )
        return list(result.scalars().all())

    async def latest_computed_at(self) -> dict[uuid.UUID, datetime]:
        """When each placement that has a snapshot was last recomputed."""
        result = await self.session.execute(
            select(
                HealthSnapshot.placement_id, func.max(HealthSnapshot.computed_at)
            ).group_by(HealthSnapshot.placement_id)
        )
        return {placement_id: at for placement_id, at in result.all()}

    async def open_flags(self, placement_id: uuid.UUID) -> list[RiskFlag]:
        """The placement's flags not yet closed, oldest first."""
        result = await self.session.execute(
            select(RiskFlag)
            .where(RiskFlag.placement_id == placement_id, RiskFlag.closed_at.is_(None))
            .order_by(RiskFlag.opened_at, RiskFlag.id)
        )
        return list(result.scalars().all())

    async def open_flags_for(
        self, placement_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, list[RiskFlag]]:
        """Each placement's flags not yet closed, oldest first."""
        if not placement_ids:
            return {}
        result = await self.session.execute(
            select(RiskFlag)
            .where(
                RiskFlag.placement_id.in_(placement_ids),
                RiskFlag.closed_at.is_(None),
            )
            .order_by(RiskFlag.opened_at, RiskFlag.id)
        )
        flags: dict[uuid.UUID, list[RiskFlag]] = {}
        for flag in result.scalars().all():
            flags.setdefault(flag.placement_id, []).append(flag)
        return flags

    async def add_flag(self, flag: RiskFlag) -> RiskFlag:
        self.session.add(flag)
        await self.session.flush()
        return flag

    @staticmethod
    def add_evidence(flag: RiskFlag, signal_ids: Collection[uuid.UUID]) -> bool:
        """Add the signals the flag does not hold yet; True when any were new."""
        known = set(flag.evidence_signal_ids)
        new = [signal_id for signal_id in signal_ids if signal_id not in known]
        if not new:
            return False
        # A new list, so the ARRAY column is seen as changed
        flag.evidence_signal_ids = [*flag.evidence_signal_ids, *new]
        return True
