"""The health recompute: one placement's evidence to a stored reading.

Loads the placement (its register context), its signals within the scoring's
reach (the lookback before the start of the trend window), its open issues
with their Technical signals, and its open flags; runs the pure health model
(``app.health``) as of now; and writes, in one transaction, a
``health_snapshots`` row and the flags the triggers call for. A trigger with
no open flag for its subject opens one; one already open gains the new
evidence. A flag the evidence no longer calls for stays open: only a person
closes it, and closing never changes a score.

The RAG level is decided after the flags, so a critical flag opened by this
recompute already keeps a green placement amber. A placement with no signal
in the lookback is stored as not scored (no scores, trend or level), and can
still have flags (contract horizon).
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.health_repo import HealthRepository
from app.db.repositories.signal_repo import SignalRepository
from app.health.config import HealthConfig, load_health_config
from app.health.scoring import (
    HealthScore,
    PlacementContext,
    SignalInput,
    assess,
    risk_level,
)
from app.health.triggers import IssueInput, TriggerHit, evaluate_triggers
from app.models.enums import (
    Dimension,
    ExtensionStatus,
    FlagSeverity,
    IssueStatus,
    PlacementStatus,
    Polarity,
    SignalIndicator,
    SnapshotReason,
)
from app.models.health import HealthSnapshot, RiskFlag
from app.models.register import Placement
from app.models.signal import Signal

logger = logging.getLogger(__name__)


def signal_input(signal: Signal) -> SignalInput:
    return SignalInput(
        id=signal.id,
        dimension=Dimension(signal.dimension),
        polarity=Polarity(signal.polarity),
        severity=signal.severity,
        confidence=signal.confidence,
        occurred_at=signal.occurred_at,
        indicator=SignalIndicator(signal.indicator) if signal.indicator else None,
        issue_id=signal.issue_id,
    )


def placement_context(placement: Placement) -> PlacementContext:
    return PlacementContext(
        start_date=placement.start_date,
        expected_end_date=placement.expected_end_date,
        extension_status=ExtensionStatus(placement.extension_status),
        status=PlacementStatus(placement.status),
    )


def snapshot_evidence(score: HealthScore) -> dict[str, Any]:
    """Per dimension: the signal count and the top contributors."""
    return {
        dimension.value: {
            "signal_count": reading.signal_count,
            "contributors": [
                {
                    "signal_id": str(c.signal_id),
                    "weight": c.weight,
                    "value": c.value,
                }
                for c in reading.contributors
            ],
        }
        for dimension, reading in score.dimensions.items()
    }


class HealthService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        config: HealthConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.health = HealthRepository(db)
        self.signals = SignalRepository(db)
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))

    async def recompute(
        self, placement_id: uuid.UUID, reason: SnapshotReason
    ) -> HealthSnapshot | None:
        """Score the placement now, store the snapshot and flags, and commit.

        ``None`` when the placement no longer exists.
        """
        placement = await self.db.get(Placement, placement_id)
        if placement is None:
            logger.warning("Health recompute: placement %s not found", placement_id)
            return None
        config = self._config or load_health_config(settings.health_config_version)
        tz = ZoneInfo(settings.health_timezone)
        as_of = self._clock()
        context = placement_context(placement)

        since = as_of - timedelta(days=config.lookback_days + config.trend.window_days)
        signals = [
            signal_input(row)
            for row in await self.signals.for_placement(placement_id, since)
        ]
        issues = [
            IssueInput(
                id=issue.id,
                status=IssueStatus(issue.status),
                occurrence_count=issue.occurrence_count,
                first_seen_at=issue.first_seen_at,
                technical_signal_ids=tuple(technical),
            )
            for issue, technical in (
                await self.signals.open_issues_with_technical_signals(placement_id)
            )
        ]
        result = assess(signals, context, as_of, config, tz)
        hits = evaluate_triggers(
            signals=signals,
            issues=issues,
            context=context,
            result=result,
            as_of=as_of,
            config=config,
            tz=tz,
        )
        open_flags, opened, extended = await self._apply_flags(
            placement_id, hits, as_of
        )

        now = result.now
        critical = any(
            flag.severity == FlagSeverity.CRITICAL.value for flag in open_flags
        )
        level = risk_level(now.overall, critical, config)
        scores = {d: now.dimensions[d].score for d in now.dimensions}
        snapshot = await self.health.add_snapshot(
            HealthSnapshot(
                placement_id=placement_id,
                computed_at=as_of,
                reason=reason.value,
                scored=now.scored,
                delivery=scores.get(Dimension.DELIVERY),
                technical=scores.get(Dimension.TECHNICAL),
                relationship=scores.get(Dimension.RELATIONSHIP),
                engagement=scores.get(Dimension.ENGAGEMENT),
                onboarding=scores.get(Dimension.ONBOARDING),
                communication=scores.get(Dimension.COMMUNICATION),
                overall=now.overall,
                trend=result.trend.value if result.trend else None,
                trend_delta=result.trend_delta,
                technical_trend=(
                    result.technical_trend.value if result.technical_trend else None
                ),
                technical_trend_delta=result.technical_trend_delta,
                risk_level=level.value if level else None,
                signal_count=now.signal_count,
                weights_version=config.version,
                evidence=snapshot_evidence(now),
            )
        )
        await self.db.commit()
        logger.info(
            "Health of placement %s (%s): %s, overall %s, trend %s; "
            "%d flag(s) opened, %d given new evidence",
            placement_id,
            reason.value,
            level.value if level else "not scored",
            now.overall,
            result.trend.value if result.trend else "none",
            len(opened),
            len(extended),
        )
        return snapshot

    async def _apply_flags(
        self, placement_id: uuid.UUID, hits: Iterable[TriggerHit], as_of: datetime
    ) -> tuple[list[RiskFlag], list[RiskFlag], list[RiskFlag]]:
        """Open a flag per new hit, extend the open ones; return (every open
        flag, those opened, those given new evidence)."""
        open_flags = await self.health.open_flags(placement_id)
        by_key = {(flag.trigger, flag.subject_key): flag for flag in open_flags}
        opened: list[RiskFlag] = []
        extended: list[RiskFlag] = []
        for hit in hits:
            flag = by_key.get((hit.trigger.value, hit.subject_key))
            if flag is None:
                flag = await self.health.add_flag(
                    RiskFlag(
                        placement_id=placement_id,
                        trigger=hit.trigger.value,
                        severity=hit.severity.value,
                        subject_key=hit.subject_key,
                        opened_at=as_of,
                        evidence_signal_ids=list(hit.evidence_signal_ids),
                    )
                )
                by_key[(flag.trigger, flag.subject_key)] = flag
                opened.append(flag)
            elif self.health.add_evidence(flag, hit.evidence_signal_ids):
                extended.append(flag)
        return list(by_key.values()), opened, extended
