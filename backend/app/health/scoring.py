"""Signals to a health reading: six dimension scores, overall, trend, RAG.

Pure and deterministic: the same signals, placement and configuration at the
same time give the same numbers, every time. Nothing here reads the database
or the clock; the caller passes ``as_of`` and the time zone.

A dimension's score is a decayed average that always includes a prior::

    score = (P * prior + sum(w_i * v_i)) / (P + sum(w_i))
    w_i   = confidence_i * 0.5 ** (age_days_i / half_life_days)

where ``v_i`` is the signal's value (positive, neutral, or negative by
severity). One signal moves a score without pinning it, and a dimension with
no signals sits at the prior. Only signals whose call was within the lookback
are read; a placement with none is not scored. Every score is rounded to one
decimal before anything compares it, so what the board shows is what decided
the RAG level and the trend.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.health.config import HealthConfig
from app.models.enums import (
    Dimension,
    ExtensionStatus,
    PlacementStatus,
    Polarity,
    RiskLevel,
    SignalIndicator,
    Trend,
)

_ONE_DECIMAL = Decimal("0.1")
_SECONDS_PER_DAY = 86_400


def round1(value: float) -> float:
    """Round half up to one decimal (6.85 -> 6.9), from the float's shortest form."""
    return float(Decimal(repr(value)).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class SignalInput:
    """What the health model reads of a stored signal."""

    id: uuid.UUID
    dimension: Dimension
    polarity: Polarity
    severity: int
    confidence: float
    occurred_at: datetime
    indicator: SignalIndicator | None = None
    issue_id: uuid.UUID | None = None


@dataclass(frozen=True)
class PlacementContext:
    """What the health model reads of the register."""

    start_date: date
    expected_end_date: date | None
    extension_status: ExtensionStatus
    status: PlacementStatus


@dataclass(frozen=True)
class Contributor:
    signal_id: uuid.UUID
    weight: float
    value: float


@dataclass(frozen=True)
class DimensionScore:
    score: float
    signal_count: int
    # The signals that pulled the score furthest from the prior, largest first.
    contributors: tuple[Contributor, ...]


@dataclass(frozen=True)
class HealthScore:
    """A placement's scores at one moment; empty when not scored."""

    scored: bool
    signal_count: int
    overall: float | None = None
    dimensions: Mapping[Dimension, DimensionScore] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthResult:
    """The reading now, the one a trend window earlier, and the trend between:
    of the overall, and of the Technical score alone (what an SME sees)."""

    now: HealthScore
    past: HealthScore
    trend: Trend | None
    trend_delta: float | None
    technical_trend: Trend | None = None
    technical_trend_delta: float | None = None


def signal_value(signal: SignalInput, config: HealthConfig) -> float:
    if signal.polarity == Polarity.POSITIVE:
        return config.values.positive
    if signal.polarity == Polarity.NEUTRAL:
        return config.values.neutral
    return config.values.negative[signal.severity]


def signal_weight(signal: SignalInput, as_of: datetime, config: HealthConfig) -> float:
    age_days = (as_of - signal.occurred_at).total_seconds() / _SECONDS_PER_DAY
    decay: float = 0.5 ** (age_days / config.half_life_days)
    return signal.confidence * decay


def in_lookback(
    signals: Iterable[SignalInput], as_of: datetime, config: HealthConfig
) -> list[SignalInput]:
    """The signals whose call was within the lookback, up to ``as_of``."""
    earliest = as_of - timedelta(days=config.lookback_days)
    return [s for s in signals if earliest <= s.occurred_at <= as_of]


def local_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


def dimension_weights(
    start_date: date, day: date, config: HealthConfig
) -> dict[Dimension, float]:
    """The weights in percent on ``day``; Onboarding weighs more early on."""
    weights = dict(config.weights)
    if (day - start_date).days >= config.early_days:
        return weights
    usual = weights[Dimension.ONBOARDING]
    scale = (100 - config.onboarding_early_weight) / (100 - usual)
    early = {dimension: weight * scale for dimension, weight in weights.items()}
    early[Dimension.ONBOARDING] = config.onboarding_early_weight
    return early


def _dimension_score(
    signals: Sequence[SignalInput], as_of: datetime, config: HealthConfig
) -> DimensionScore:
    total_weight = config.prior_weight
    total = config.prior_weight * config.prior
    pulls: list[tuple[float, SignalInput, float, float]] = []
    for signal in signals:
        weight = signal_weight(signal, as_of, config)
        value = signal_value(signal, config)
        total_weight += weight
        total += weight * value
        pull = weight * abs(value - config.prior)
        if pull > 0:
            pulls.append((pull, signal, weight, value))
    pulls.sort(key=lambda p: (-p[0], -p[1].occurred_at.timestamp(), str(p[1].id)))
    contributors = tuple(
        Contributor(signal_id=signal.id, weight=round(weight, 4), value=value)
        for _, signal, weight, value in pulls[: config.top_contributors]
    )
    return DimensionScore(
        score=round1(total / total_weight),
        signal_count=len(signals),
        contributors=contributors,
    )


def score_at(
    signals: Iterable[SignalInput],
    start_date: date,
    as_of: datetime,
    config: HealthConfig,
    tz: ZoneInfo,
) -> HealthScore:
    """The placement's scores from the signals known up to ``as_of``."""
    window = in_lookback(signals, as_of, config)
    if not window:
        return HealthScore(scored=False, signal_count=0)
    dimensions = {
        dimension: _dimension_score(
            [s for s in window if s.dimension == dimension], as_of, config
        )
        for dimension in Dimension
    }
    weights = dimension_weights(start_date, local_date(as_of, tz), config)
    overall = round1(sum(weights[d] * dimensions[d].score for d in Dimension) / 100)
    return HealthScore(
        scored=True,
        signal_count=len(window),
        overall=overall,
        dimensions=dimensions,
    )


def trend_between(
    now: HealthScore, past: HealthScore, config: HealthConfig
) -> tuple[Trend | None, float | None]:
    """Up, flat or down, and by how much; none until both moments are scored."""
    return _trend(now.overall, past.overall, config)


def dimension_trend_between(
    now: HealthScore, past: HealthScore, dimension: Dimension, config: HealthConfig
) -> tuple[Trend | None, float | None]:
    """The same for one dimension's score."""
    return _trend(
        _dimension_value(now, dimension), _dimension_value(past, dimension), config
    )


def _dimension_value(score: HealthScore, dimension: Dimension) -> float | None:
    reading = score.dimensions.get(dimension)
    return reading.score if reading is not None else None


def _trend(
    now: float | None, past: float | None, config: HealthConfig
) -> tuple[Trend | None, float | None]:
    if now is None or past is None:
        return None, None
    delta = round1(now - past)
    if delta > config.trend.flat_band:
        return Trend.UP, delta
    if delta < -config.trend.flat_band:
        return Trend.DOWN, delta
    return Trend.FLAT, delta


def assess(
    signals: Sequence[SignalInput],
    context: PlacementContext,
    as_of: datetime,
    config: HealthConfig,
    tz: ZoneInfo,
) -> HealthResult:
    """Score now and a trend window ago (signals by when they were said)."""
    now = score_at(signals, context.start_date, as_of, config, tz)
    then = as_of - timedelta(days=config.trend.window_days)
    past = score_at(signals, context.start_date, then, config, tz)
    trend, delta = trend_between(now, past, config)
    technical, technical_delta = dimension_trend_between(
        now, past, Dimension.TECHNICAL, config
    )
    return HealthResult(
        now=now,
        past=past,
        trend=trend,
        trend_delta=delta,
        technical_trend=technical,
        technical_trend_delta=technical_delta,
    )


def risk_level(
    overall: float | None, has_open_critical_flag: bool, config: HealthConfig
) -> RiskLevel | None:
    """Green, amber or red; an open critical flag keeps it at least amber."""
    if overall is None:
        return None
    if overall >= config.rag.green_min:
        level = RiskLevel.GREEN
    elif overall >= config.rag.amber_min:
        level = RiskLevel.AMBER
    else:
        level = RiskLevel.RED
    if level == RiskLevel.GREEN and has_open_critical_flag:
        return RiskLevel.AMBER
    return level
