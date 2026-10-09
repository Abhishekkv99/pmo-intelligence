"""Each early-warning trigger at its edges, with the v1 thresholds."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.health.config import load_health_config
from app.health.scoring import (
    HealthResult,
    HealthScore,
    PlacementContext,
    SignalInput,
)
from app.health.triggers import IssueInput, TriggerHit, evaluate_triggers
from app.models.enums import (
    Dimension,
    ExtensionStatus,
    FlagSeverity,
    IssueStatus,
    PlacementStatus,
    Polarity,
    RiskTrigger,
    SignalIndicator,
    Trend,
)

CONFIG = load_health_config("v1")
TZ = ZoneInfo("Europe/London")
AS_OF = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
NO_RESULT = HealthResult(
    now=HealthScore(scored=False, signal_count=0),
    past=HealthScore(scored=False, signal_count=0),
    trend=None,
    trend_delta=None,
)


def _signal(
    dimension: Dimension = Dimension.DELIVERY,
    polarity: Polarity = Polarity.NEGATIVE,
    *,
    severity: int = 1,
    days_ago: float = 0,
    indicator: SignalIndicator | None = None,
) -> SignalInput:
    return SignalInput(
        id=uuid.uuid4(),
        dimension=dimension,
        polarity=polarity,
        severity=severity,
        confidence=0.8,
        occurred_at=AS_OF - timedelta(days=days_ago),
        indicator=indicator,
    )


def _context(
    *,
    status: PlacementStatus = PlacementStatus.ACTIVE,
    end: date | None = None,
    extension: ExtensionStatus = ExtensionStatus.NOT_DUE,
) -> PlacementContext:
    return PlacementContext(
        start_date=date(2026, 6, 1),
        expected_end_date=end,
        extension_status=extension,
        status=status,
    )


def _evaluate(
    signals: list[SignalInput] | None = None,
    *,
    issues: list[IssueInput] | None = None,
    context: PlacementContext | None = None,
    result: HealthResult = NO_RESULT,
    as_of: datetime = AS_OF,
) -> list[TriggerHit]:
    return evaluate_triggers(
        signals=signals or [],
        issues=issues or [],
        context=context or _context(),
        result=result,
        as_of=as_of,
        config=CONFIG,
        tz=TZ,
    )


def _triggers(hits: list[TriggerHit]) -> list[RiskTrigger]:
    return [hit.trigger for hit in hits]


def _with_delta(delta: float) -> HealthResult:
    scored = HealthScore(scored=True, signal_count=1, overall=6.0)
    return HealthResult(now=scored, past=scored, trend=Trend.DOWN, trend_delta=delta)


class TestCriticalIndicators:
    @pytest.mark.parametrize(
        "indicator",
        [
            SignalIndicator.CLIENT_DISSATISFACTION,
            SignalIndicator.CONSULTANT_CHANGE_REQUESTED,
        ],
    )
    def test_a_client_indicator_raises_client_dissatisfaction(
        self, indicator: SignalIndicator
    ) -> None:
        signal = _signal(indicator=indicator, days_ago=40)
        [hit] = _evaluate([signal])
        assert hit == TriggerHit(
            trigger=RiskTrigger.CLIENT_DISSATISFACTION,
            severity=FlagSeverity.CRITICAL,
            subject_key="",
            evidence_signal_ids=(signal.id,),
        )

    def test_intent_to_leave_is_critical(self) -> None:
        signal = _signal(
            Dimension.ENGAGEMENT, indicator=SignalIndicator.INTENT_TO_LEAVE
        )
        [hit] = _evaluate([signal])
        assert hit.trigger == RiskTrigger.INTENT_TO_LEAVE
        assert hit.severity == FlagSeverity.CRITICAL

    def test_an_indicator_older_than_the_lookback_raises_nothing(self) -> None:
        old = _signal(indicator=SignalIndicator.INTENT_TO_LEAVE, days_ago=91)
        assert _evaluate([old]) == []

    def test_evidence_is_every_tagged_signal_oldest_first(self) -> None:
        newer = _signal(indicator=SignalIndicator.CLIENT_DISSATISFACTION, days_ago=1)
        older = _signal(
            indicator=SignalIndicator.CONSULTANT_CHANGE_REQUESTED, days_ago=5
        )
        untagged = _signal(severity=3)
        [hit] = _evaluate([newer, untagged, older])
        assert hit.evidence_signal_ids == (older.id, newer.id)


class TestRepeatedBlocker:
    def _issue(
        self,
        *,
        count: int = 1,
        days_open: float = 1,
        status: IssueStatus = IssueStatus.OPEN,
        technical: int = 1,
    ) -> IssueInput:
        return IssueInput(
            id=uuid.uuid4(),
            status=status,
            occurrence_count=count,
            first_seen_at=AS_OF - timedelta(days=days_open),
            technical_signal_ids=tuple(uuid.uuid4() for _ in range(technical)),
        )

    def test_a_technical_issue_seen_in_two_calls_is_a_repeated_blocker(
        self,
    ) -> None:
        issue = self._issue(count=2, technical=2)
        [hit] = _evaluate(issues=[issue])
        assert hit.trigger == RiskTrigger.REPEATED_BLOCKER
        assert hit.severity == FlagSeverity.HIGH
        assert hit.subject_key == str(issue.id)
        assert hit.evidence_signal_ids == issue.technical_signal_ids

    def test_open_more_than_10_days_is_a_repeated_blocker(self) -> None:
        exactly_ten = self._issue(days_open=10)
        just_over = self._issue(days_open=10 + 1 / 86_400)
        hits = _evaluate(issues=[exactly_ten, just_over])
        assert [hit.subject_key for hit in hits] == [str(just_over.id)]

    def test_an_issue_without_a_technical_signal_is_not_a_blocker(self) -> None:
        assert _evaluate(issues=[self._issue(count=3, technical=0)]) == []

    def test_a_resolved_issue_is_not_a_blocker(self) -> None:
        resolved = self._issue(count=3, status=IssueStatus.RESOLVED)
        assert _evaluate(issues=[resolved]) == []

    def test_each_issue_is_its_own_flag(self) -> None:
        first = self._issue(count=2, days_open=20)
        second = self._issue(count=2, days_open=5)
        hits = _evaluate(issues=[second, first])
        assert [hit.subject_key for hit in hits] == [str(first.id), str(second.id)]


class TestDownwardTrend:
    def test_a_fall_of_1_5_raises_it_with_the_recent_negatives(self) -> None:
        fresh = _signal(severity=3, days_ago=2)
        old = _signal(severity=3, days_ago=14)
        praise = _signal(polarity=Polarity.POSITIVE, days_ago=1)
        [hit] = _evaluate([fresh, old, praise], result=_with_delta(-1.5))
        assert hit.trigger == RiskTrigger.DOWNWARD_TREND
        assert hit.evidence_signal_ids == (fresh.id,)

    def test_a_smaller_fall_raises_nothing(self) -> None:
        assert _evaluate(result=_with_delta(-1.4)) == []

    def test_no_trend_raises_nothing(self) -> None:
        assert _evaluate(result=NO_RESULT) == []


class TestRelationshipStrain:
    def test_one_severity_3_within_14_days(self) -> None:
        signal = _signal(Dimension.RELATIONSHIP, severity=3, days_ago=14)
        [hit] = _evaluate([signal])
        assert hit.trigger == RiskTrigger.RELATIONSHIP_STRAIN
        assert hit.evidence_signal_ids == (signal.id,)

    def test_a_severity_3_older_than_14_days_raises_nothing(self) -> None:
        old = _signal(Dimension.RELATIONSHIP, severity=3, days_ago=15)
        assert _evaluate([old]) == []

    def test_one_severity_2_alone_raises_nothing(self) -> None:
        assert _evaluate([_signal(Dimension.RELATIONSHIP, severity=2)]) == []

    def test_two_severity_2_within_14_days(self) -> None:
        first = _signal(Dimension.RELATIONSHIP, severity=2, days_ago=10)
        second = _signal(Dimension.RELATIONSHIP, severity=2, days_ago=1)
        [hit] = _evaluate([second, first])
        assert hit.evidence_signal_ids == (first.id, second.id)

    def test_a_pair_split_by_the_window_raises_nothing(self) -> None:
        inside = _signal(Dimension.RELATIONSHIP, severity=2, days_ago=1)
        outside = _signal(Dimension.RELATIONSHIP, severity=2, days_ago=15)
        assert _evaluate([inside, outside]) == []

    def test_severity_2_and_3_are_both_evidence(self) -> None:
        notable = _signal(Dimension.RELATIONSHIP, severity=2, days_ago=3)
        serious = _signal(Dimension.RELATIONSHIP, severity=3, days_ago=1)
        minor = _signal(Dimension.RELATIONSHIP, severity=1)
        [hit] = _evaluate([minor, serious, notable])
        assert hit.evidence_signal_ids == (notable.id, serious.id)

    @pytest.mark.parametrize(
        ("dimension", "polarity"),
        [
            (Dimension.RELATIONSHIP, Polarity.POSITIVE),
            (Dimension.ENGAGEMENT, Polarity.NEGATIVE),
        ],
    )
    def test_only_negative_relationship_signals_count(
        self, dimension: Dimension, polarity: Polarity
    ) -> None:
        assert _evaluate([_signal(dimension, polarity, severity=3)]) == []


class TestContractHorizon:
    def test_an_end_30_days_ahead_without_a_confirmed_extension(self) -> None:
        [hit] = _evaluate(context=_context(end=date(2026, 11, 19)))
        assert hit.trigger == RiskTrigger.CONTRACT_HORIZON
        assert hit.severity == FlagSeverity.HIGH
        assert hit.evidence_signal_ids == ()

    def test_an_end_31_days_ahead_raises_nothing(self) -> None:
        assert _evaluate(context=_context(end=date(2026, 11, 20))) == []

    def test_an_end_already_passed_still_raises_it(self) -> None:
        hits = _evaluate(context=_context(end=date(2026, 9, 30)))
        assert _triggers(hits) == [RiskTrigger.CONTRACT_HORIZON]

    def test_a_confirmed_extension_raises_nothing(self) -> None:
        context = _context(end=date(2026, 11, 1), extension=ExtensionStatus.CONFIRMED)
        assert _evaluate(context=context) == []

    def test_no_expected_end_raises_nothing(self) -> None:
        assert _evaluate(context=_context(end=None)) == []

    def test_today_is_the_uk_date(self) -> None:
        # 23:30 UTC on 20 Oct is 00:30 on 21 Oct in London: 20 Nov is 30 days on.
        late_evening = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
        hits = _evaluate(context=_context(end=date(2026, 11, 20)), as_of=late_evening)
        assert _triggers(hits) == [RiskTrigger.CONTRACT_HORIZON]


class TestAllTogether:
    def test_an_ended_placement_raises_no_new_flags(self) -> None:
        context = _context(status=PlacementStatus.ENDED, end=date(2026, 10, 1))
        signals = [_signal(indicator=SignalIndicator.INTENT_TO_LEAVE)]
        assert _evaluate(signals, context=context) == []

    def test_hits_come_in_the_enumerations_order(self) -> None:
        signals = [
            _signal(indicator=SignalIndicator.INTENT_TO_LEAVE),
            _signal(Dimension.RELATIONSHIP, severity=3),
            _signal(indicator=SignalIndicator.CLIENT_DISSATISFACTION),
        ]
        issue = IssueInput(
            id=uuid.uuid4(),
            status=IssueStatus.OPEN,
            occurrence_count=2,
            first_seen_at=AS_OF - timedelta(days=3),
            technical_signal_ids=(uuid.uuid4(),),
        )
        hits = _evaluate(
            signals,
            issues=[issue],
            context=_context(end=date(2026, 11, 1)),
            result=_with_delta(-2.0),
        )
        assert _triggers(hits) == [
            RiskTrigger.CLIENT_DISSATISFACTION,
            RiskTrigger.REPEATED_BLOCKER,
            RiskTrigger.DOWNWARD_TREND,
            RiskTrigger.RELATIONSHIP_STRAIN,
            RiskTrigger.CONTRACT_HORIZON,
            RiskTrigger.INTENT_TO_LEAVE,
        ]
