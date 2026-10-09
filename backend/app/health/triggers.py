"""Early-warning triggers: which risk flags a placement's evidence calls for.

Pure, like the scoring: the caller passes the signals, the placement's
issues, the register context, the reading from ``scoring.assess`` and the
time. Each hit names its trigger, severity, subject (the issue id for a
repeated blocker, ``''`` otherwise) and the signals behind it; opening a flag,
or adding the evidence to the one already open, is the caller's job.

Evaluated now (PRD Phase 2): client dissatisfaction and intent to leave
(critical; any tagged signal in the lookback), repeated blocker, downward
trend, relationship strain and contract horizon (high). Gone quiet and missed
commitment come with Teams chat. An ended or terminated placement raises no
new flags.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.health.config import HealthConfig
from app.health.scoring import (
    HealthResult,
    PlacementContext,
    SignalInput,
    in_lookback,
    local_date,
)
from app.models.enums import (
    RISK_TRIGGER_SEVERITY,
    Dimension,
    ExtensionStatus,
    FlagSeverity,
    IssueStatus,
    PlacementStatus,
    Polarity,
    RiskTrigger,
    SignalIndicator,
)

NO_SUBJECT = ""

CLIENT_INDICATORS = frozenset(
    {
        SignalIndicator.CLIENT_DISSATISFACTION,
        SignalIndicator.CONSULTANT_CHANGE_REQUESTED,
    }
)


@dataclass(frozen=True)
class IssueInput:
    """What the repeated-blocker trigger reads of an issue."""

    id: uuid.UUID
    status: IssueStatus
    occurrence_count: int
    first_seen_at: datetime
    # Its signals on the Technical dimension, whenever they were said.
    technical_signal_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class TriggerHit:
    trigger: RiskTrigger
    severity: FlagSeverity
    subject_key: str
    evidence_signal_ids: tuple[uuid.UUID, ...]


def _hit(
    trigger: RiskTrigger,
    evidence: Iterable[SignalInput] = (),
    subject_key: str = NO_SUBJECT,
) -> TriggerHit:
    ordered = sorted(evidence, key=lambda s: (s.occurred_at, str(s.id)))
    return TriggerHit(
        trigger=trigger,
        severity=RISK_TRIGGER_SEVERITY[trigger],
        subject_key=subject_key,
        evidence_signal_ids=tuple(s.id for s in ordered),
    )


def _indicated(
    signals: Sequence[SignalInput], indicators: Iterable[SignalIndicator]
) -> list[SignalInput]:
    wanted = set(indicators)
    return [s for s in signals if s.indicator in wanted]


def _repeated_blockers(
    issues: Iterable[IssueInput], as_of: datetime, config: HealthConfig
) -> list[TriggerHit]:
    rule = config.triggers.repeated_blocker
    hits = []
    for issue in sorted(issues, key=lambda i: (i.first_seen_at, str(i.id))):
        if issue.status != IssueStatus.OPEN or not issue.technical_signal_ids:
            continue
        repeated = issue.occurrence_count >= rule.min_occurrences
        lingering = as_of - issue.first_seen_at > timedelta(days=rule.open_days)
        if repeated or lingering:
            hits.append(
                TriggerHit(
                    trigger=RiskTrigger.REPEATED_BLOCKER,
                    severity=RISK_TRIGGER_SEVERITY[RiskTrigger.REPEATED_BLOCKER],
                    subject_key=str(issue.id),
                    evidence_signal_ids=issue.technical_signal_ids,
                )
            )
    return hits


def _relationship_strain(
    signals: Sequence[SignalInput], as_of: datetime, config: HealthConfig
) -> TriggerHit | None:
    rule = config.triggers.relationship_strain
    since = as_of - timedelta(days=rule.window_days)
    negative = [
        s
        for s in signals
        if s.dimension == Dimension.RELATIONSHIP
        and s.polarity == Polarity.NEGATIVE
        and since <= s.occurred_at <= as_of
    ]
    single = [s for s in negative if s.severity >= rule.single_severity]
    pair = [s for s in negative if s.severity >= rule.pair_severity]
    if not single and len(pair) < rule.pair_count:
        return None
    return _hit(RiskTrigger.RELATIONSHIP_STRAIN, {*single, *pair})


def _downward_trend(
    signals: Sequence[SignalInput],
    result: HealthResult,
    as_of: datetime,
    config: HealthConfig,
) -> TriggerHit | None:
    delta = result.trend_delta
    if delta is None or delta > -config.triggers.downward_trend.drop:
        return None
    since = as_of - timedelta(days=config.trend.window_days)
    fresh_negatives = [
        s
        for s in signals
        if s.polarity == Polarity.NEGATIVE and since < s.occurred_at <= as_of
    ]
    return _hit(RiskTrigger.DOWNWARD_TREND, fresh_negatives)


def _contract_horizon(
    context: PlacementContext, as_of: datetime, config: HealthConfig, tz: ZoneInfo
) -> TriggerHit | None:
    end = context.expected_end_date
    if end is None or context.extension_status == ExtensionStatus.CONFIRMED:
        return None
    days = config.triggers.contract_horizon.days
    horizon = local_date(as_of, tz) + timedelta(days=days)
    if end > horizon:
        return None
    return _hit(RiskTrigger.CONTRACT_HORIZON)


def evaluate_triggers(
    *,
    signals: Sequence[SignalInput],
    issues: Iterable[IssueInput],
    context: PlacementContext,
    result: HealthResult,
    as_of: datetime,
    config: HealthConfig,
    tz: ZoneInfo,
) -> list[TriggerHit]:
    """Every trigger the evidence fires now, in the enumeration's order."""
    if context.status != PlacementStatus.ACTIVE:
        return []
    recent = in_lookback(signals, as_of, config)
    hits: list[TriggerHit] = []

    client = _indicated(recent, CLIENT_INDICATORS)
    if client:
        hits.append(_hit(RiskTrigger.CLIENT_DISSATISFACTION, client))
    hits.extend(_repeated_blockers(issues, as_of, config))
    downward = _downward_trend(recent, result, as_of, config)
    if downward is not None:
        hits.append(downward)
    strain = _relationship_strain(recent, as_of, config)
    if strain is not None:
        hits.append(strain)
    horizon = _contract_horizon(context, as_of, config, tz)
    if horizon is not None:
        hits.append(horizon)
    leaving = _indicated(recent, {SignalIndicator.INTENT_TO_LEAVE})
    if leaving:
        hits.append(_hit(RiskTrigger.INTENT_TO_LEAVE, leaving))
    return hits
