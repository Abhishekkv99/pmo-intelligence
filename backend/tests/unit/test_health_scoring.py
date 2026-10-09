"""The scoring module with fixed signal sets: exact scores, trend and RAG.

Every expected number here was worked out by hand from the formula in
``app/health/scoring.py`` and the v1 configuration (prior 7.0 with weight 1,
half-life 14 days, values 9 / 7 / 5-3-1), not read back from the code.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.health.config import load_health_config
from app.health.scoring import (
    HealthScore,
    PlacementContext,
    SignalInput,
    assess,
    dimension_weights,
    risk_level,
    round1,
    score_at,
    trend_between,
)
from app.models.enums import (
    Dimension,
    ExtensionStatus,
    PlacementStatus,
    Polarity,
    RiskLevel,
    Trend,
)

CONFIG = load_health_config("v1")
TZ = ZoneInfo("Europe/London")
AS_OF = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
# Long past the 30-day onboarding window.
SETTLED_START = date(2026, 6, 1)


def _signal(
    dimension: Dimension,
    polarity: Polarity,
    *,
    severity: int = 1,
    confidence: float = 1.0,
    days_ago: float = 0,
) -> SignalInput:
    return SignalInput(
        id=uuid.uuid4(),
        dimension=dimension,
        polarity=polarity,
        severity=severity,
        confidence=confidence,
        occurred_at=AS_OF - timedelta(days=days_ago),
    )


def _score(signals: list[SignalInput], start: date = SETTLED_START) -> HealthScore:
    return score_at(signals, start, AS_OF, CONFIG, TZ)


def _context(start: date = SETTLED_START) -> PlacementContext:
    return PlacementContext(
        start_date=start,
        expected_end_date=None,
        extension_status=ExtensionStatus.NOT_DUE,
        status=PlacementStatus.ACTIVE,
    )


class TestRounding:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(6.85, 6.9), (6.849, 6.8), (6.95, 7.0), (-0.45, -0.5), (4.0, 4.0)],
    )
    def test_round1_rounds_half_up_to_one_decimal(
        self, value: float, expected: float
    ) -> None:
        assert round1(value) == expected


class TestNotScored:
    def test_no_signals_is_not_scored(self) -> None:
        score = _score([])
        assert score == HealthScore(scored=False, signal_count=0)

    def test_signals_only_before_the_lookback_are_not_scored(self) -> None:
        score = _score([_signal(Dimension.DELIVERY, Polarity.NEGATIVE, days_ago=91)])
        assert not score.scored
        assert score.overall is None

    def test_a_signal_exactly_at_the_lookback_edge_counts(self) -> None:
        score = _score([_signal(Dimension.DELIVERY, Polarity.NEGATIVE, days_ago=90)])
        assert score.scored
        assert score.signal_count == 1

    def test_a_signal_after_as_of_is_not_read(self) -> None:
        later = _signal(Dimension.DELIVERY, Polarity.NEGATIVE, days_ago=-1)
        assert not _score([later]).scored


class TestDimensionScore:
    def test_one_fresh_serious_negative_moves_but_does_not_pin(self) -> None:
        # (7 + 0.9 * 1) / (1 + 0.9) = 4.158 -> 4.2
        score = _score(
            [
                _signal(
                    Dimension.TECHNICAL, Polarity.NEGATIVE, severity=3, confidence=0.9
                )
            ]
        )
        assert score.dimensions[Dimension.TECHNICAL].score == 4.2

    def test_dimensions_without_signals_sit_at_the_prior(self) -> None:
        score = _score([_signal(Dimension.TECHNICAL, Polarity.NEGATIVE, severity=3)])
        for dimension in Dimension:
            if dimension != Dimension.TECHNICAL:
                assert score.dimensions[dimension].score == 7.0
                assert score.dimensions[dimension].signal_count == 0

    @pytest.mark.parametrize(
        ("days_ago", "expected"),
        # weight 0.9 * 0.5 ** (age / 14): 0.45 at 14 days, 0.225 at 28.
        [(14, 5.1), (28, 5.9)],
    )
    def test_a_signal_fades_with_its_half_life(
        self, days_ago: float, expected: float
    ) -> None:
        signal = _signal(
            Dimension.TECHNICAL,
            Polarity.NEGATIVE,
            severity=3,
            confidence=0.9,
            days_ago=days_ago,
        )
        assert _score([signal]).dimensions[Dimension.TECHNICAL].score == expected

    @pytest.mark.parametrize(
        ("polarity", "severity", "expected"),
        # (7 + v) / 2 at full confidence, age 0.
        [
            (Polarity.POSITIVE, 1, 8.0),
            (Polarity.NEUTRAL, 3, 7.0),
            (Polarity.NEGATIVE, 1, 6.0),
            (Polarity.NEGATIVE, 2, 5.0),
            (Polarity.NEGATIVE, 3, 4.0),
        ],
    )
    def test_value_by_polarity_and_severity(
        self, polarity: Polarity, severity: int, expected: float
    ) -> None:
        signal = _signal(Dimension.DELIVERY, polarity, severity=severity)
        assert _score([signal]).dimensions[Dimension.DELIVERY].score == expected

    def test_confidence_scales_a_signals_weight(self) -> None:
        # (7 + 0.5 * 9) / 1.5 = 7.667 -> 7.7
        signal = _signal(Dimension.DELIVERY, Polarity.POSITIVE, confidence=0.5)
        assert _score([signal]).dimensions[Dimension.DELIVERY].score == 7.7

    def test_a_zero_confidence_signal_counts_but_weighs_nothing(self) -> None:
        signal = _signal(Dimension.DELIVERY, Polarity.NEGATIVE, confidence=0.0)
        dimension = _score([signal]).dimensions[Dimension.DELIVERY]
        assert dimension.score == 7.0
        assert dimension.signal_count == 1
        assert dimension.contributors == ()


class TestContributors:
    def test_the_largest_pulls_from_the_prior_come_first_capped_at_five(
        self,
    ) -> None:
        severe = _signal(Dimension.TECHNICAL, Polarity.NEGATIVE, severity=3)
        notable = _signal(Dimension.TECHNICAL, Polarity.NEGATIVE, severity=2)
        minor = [
            _signal(Dimension.TECHNICAL, Polarity.NEGATIVE, days_ago=d)
            for d in (1, 2, 3, 4)
        ]
        neutral = _signal(Dimension.TECHNICAL, Polarity.NEUTRAL, severity=3)

        dimension = _score([*minor, neutral, notable, severe]).dimensions[
            Dimension.TECHNICAL
        ]

        assert dimension.signal_count == 7
        assert [c.signal_id for c in dimension.contributors] == [
            severe.id,
            notable.id,
            minor[0].id,
            minor[1].id,
            minor[2].id,
        ]
        assert dimension.contributors[0].weight == 1.0
        assert dimension.contributors[0].value == 1.0

    def test_equal_pulls_go_to_the_newer_signal(self) -> None:
        older = _signal(Dimension.DELIVERY, Polarity.POSITIVE, days_ago=1)
        newer = _signal(
            Dimension.DELIVERY, Polarity.POSITIVE, confidence=0.5 ** (1 / 14)
        )
        # Both weigh 0.5 ** (1 / 14); the newer one is listed first.
        contributors = (
            _score([older, newer]).dimensions[Dimension.DELIVERY].contributors
        )
        assert [c.signal_id for c in contributors] == [newer.id, older.id]

    def test_neutral_signals_never_contribute(self) -> None:
        neutral = _signal(Dimension.ENGAGEMENT, Polarity.NEUTRAL)
        dimension = _score([neutral]).dimensions[Dimension.ENGAGEMENT]
        assert dimension.contributors == ()


class TestOverall:
    def test_overall_is_the_weighted_mean_of_the_rounded_dimensions(self) -> None:
        # Technical 4.2, the rest 7.0: (700 - 15 * 2.8) / 100 = 6.58 -> 6.6
        score = _score(
            [
                _signal(
                    Dimension.TECHNICAL, Polarity.NEGATIVE, severity=3, confidence=0.9
                )
            ]
        )
        assert score.overall == 6.6

    def test_onboarding_weighs_25_in_the_first_30_days(self) -> None:
        # Onboarding (7 + 3) / 2 = 5.0. Early: 75 * 7.0 + 25 * 5.0 = 6.5;
        # settled: 95 * 7.0 + 5 * 5.0 = 6.9.
        signal = _signal(Dimension.ONBOARDING, Polarity.NEGATIVE, severity=2)
        assert _score([signal], start=date(2026, 10, 10)).overall == 6.5
        assert _score([signal], start=date(2026, 9, 1)).overall == 6.9

    def test_the_early_window_ends_on_day_30(self) -> None:
        start = date(2026, 9, 1)
        day_29 = dimension_weights(start, start + timedelta(days=29), CONFIG)
        day_30 = dimension_weights(start, start + timedelta(days=30), CONFIG)

        assert day_29[Dimension.ONBOARDING] == 25
        assert day_29[Dimension.DELIVERY] == pytest.approx(30 * 75 / 95)
        assert sum(day_29.values()) == pytest.approx(100)
        assert day_30 == dict(CONFIG.weights)

    def test_the_early_window_uses_the_uk_date(self) -> None:
        # 23:30 UTC on 30 Sep is 00:30 on 1 Oct in London (BST): day 30.
        start = date(2026, 9, 1)
        late_evening = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
        signal = SignalInput(
            id=uuid.uuid4(),
            dimension=Dimension.ONBOARDING,
            polarity=Polarity.NEGATIVE,
            severity=2,
            confidence=1.0,
            occurred_at=late_evening,
        )
        assert score_at([signal], start, late_evening, CONFIG, TZ).overall == 6.9


class TestTrend:
    def test_trend_compares_with_the_signals_said_14_days_earlier(self) -> None:
        # 14 days ago only the praise was said: Delivery (7 + 0.743 * 9) /
        # 1.743 = 7.9, overall 7.27 -> 7.3. Now the praise has faded (7.5) and
        # Relationship is (7 + 1) / 2 = 4.0: overall 6.4, down 0.9.
        praise = _signal(Dimension.DELIVERY, Polarity.POSITIVE, days_ago=20)
        friction = _signal(Dimension.RELATIONSHIP, Polarity.NEGATIVE, severity=3)

        result = assess([praise, friction], _context(), AS_OF, CONFIG, TZ)

        assert result.past.overall == 7.3
        assert result.now.overall == 6.4
        assert result.trend == Trend.DOWN
        assert result.trend_delta == -0.9

    def test_no_trend_until_there_is_a_score_to_compare(self) -> None:
        first_call = _signal(Dimension.RELATIONSHIP, Polarity.NEGATIVE, severity=3)
        result = assess([first_call], _context(), AS_OF, CONFIG, TZ)
        assert result.now.scored
        assert not result.past.scored
        assert result.trend is None
        assert result.trend_delta is None

    @pytest.mark.parametrize(
        ("now", "past", "trend", "delta"),
        [
            (7.5, 7.0, Trend.FLAT, 0.5),
            (6.5, 7.0, Trend.FLAT, -0.5),
            (7.6, 7.0, Trend.UP, 0.6),
            (6.4, 7.0, Trend.DOWN, -0.6),
            (7.0, 7.0, Trend.FLAT, 0.0),
        ],
    )
    def test_flat_within_half_a_point_either_way(
        self, now: float, past: float, trend: Trend, delta: float
    ) -> None:
        result = trend_between(
            HealthScore(scored=True, signal_count=1, overall=now),
            HealthScore(scored=True, signal_count=1, overall=past),
            CONFIG,
        )
        assert result == (trend, delta)


class TestRiskLevel:
    @pytest.mark.parametrize(
        ("overall", "level"),
        [
            (10.0, RiskLevel.GREEN),
            (7.0, RiskLevel.GREEN),
            (6.9, RiskLevel.AMBER),
            (5.0, RiskLevel.AMBER),
            (4.9, RiskLevel.RED),
            (1.0, RiskLevel.RED),
        ],
    )
    def test_green_from_7_amber_from_5(self, overall: float, level: RiskLevel) -> None:
        assert risk_level(overall, False, CONFIG) == level

    def test_an_open_critical_flag_keeps_it_at_least_amber(self) -> None:
        assert risk_level(8.5, True, CONFIG) == RiskLevel.AMBER
        assert risk_level(6.0, True, CONFIG) == RiskLevel.AMBER
        assert risk_level(3.0, True, CONFIG) == RiskLevel.RED

    def test_not_scored_has_no_level(self) -> None:
        assert risk_level(None, True, CONFIG) is None
