"""emit_signals: only quoted, found items become drafts, placed and attributed."""

from typing import Any

import pytest

from app.ai.session.emit import build_analysis, emit_signals
from app.ai.session.schemas import ClosedAction, ExtractedAction, ExtractedIssue
from app.ai.session.state import SessionGraphState
from app.models.enums import (
    Dimension,
    Polarity,
    SignalCategory,
    SignalIndicator,
    SpeakerRole,
)
from tests.unit.session_pipeline_helpers import (
    ACTIONS,
    CLASSIFICATION,
    CLIENT,
    EARLIER_ISSUE_ID,
    ISSUES,
    OPEN_ACTION_ID,
    RELATIONSHIP,
    ROLES,
    SUMMARY,
    context,
    signal,
)


def _state(**changes: Any) -> SessionGraphState:
    state: dict[str, Any] = {
        "context": context(),
        "speakers": ROLES.speakers,
        "session_class": CLASSIFICATION.session_class.value,
        "project_phase": CLASSIFICATION.project_phase,
        "summary": SUMMARY.summary,
        "issues": ISSUES.issues,
        "relationship_signals": RELATIONSHIP.signals,
        "client_signals": CLIENT.signals,
        "actions": ACTIONS.actions,
        "closed_actions": ACTIONS.closed,
    }
    state.update(changes)
    return state  # type: ignore[return-value]


class TestFoundItems:
    def test_every_found_item_becomes_a_draft(self) -> None:
        analysis = build_analysis(_state())

        assert analysis.summary == "Priya is blocked on staging access."
        assert analysis.session_class == "check_in"
        assert analysis.project_phase == "third week"
        assert len(analysis.issues) == 1
        assert [s.category for s in analysis.signals] == [
            SignalCategory.RELATIONSHIP_ENGAGEMENT.value,
            SignalCategory.CLIENT.value,
        ]
        assert len(analysis.actions) == 1
        assert analysis.closed_action_ids == [OPEN_ACTION_ID]
        assert analysis.quotes_rejected == 0

    def test_a_signal_carries_its_speaker_s_role_and_moment(self) -> None:
        analysis = build_analysis(_state())

        relationship = analysis.signals[0]
        assert relationship.speaker_role == SpeakerRole.CONSULTANT.value
        assert relationship.offset_ms == 12_000
        issue = analysis.issues[0]
        assert issue.signal.offset_ms == 5_000
        assert issue.earlier_issue_id == EARLIER_ISSUE_ID

    def test_speaker_roles_are_kept_by_label(self) -> None:
        analysis = build_analysis(_state())

        assert analysis.speaker_roles == {
            "A": {"role": "sme", "name": "Sam Okafor"},
            "B": {"role": "consultant", "name": "Priya Shah"},
        }

    def test_without_roles_a_signal_has_no_speaker_role(self) -> None:
        analysis = build_analysis(_state(speakers=[]))

        assert analysis.signals[0].speaker_role is None
        assert analysis.speaker_roles == {}

    def test_an_action_gets_its_due_date_and_moment(self) -> None:
        action = build_analysis(_state()).actions[0]

        assert action.due_text == "by Friday"
        assert action.due_date is not None
        assert action.due_date.isoformat() == "2026-10-09"
        assert action.offset_ms == 20_000
        assert action.owner_role == "sme"


class TestRejected:
    def test_items_whose_quote_is_not_in_the_transcript_are_dropped_and_counted(
        self,
    ) -> None:
        made_up = "I am thinking of leaving."
        issue = ISSUES.issues[0].model_copy(update={"quote": made_up})
        action = ACTIONS.actions[0].model_copy(update={"quote": made_up})
        closure = ClosedAction(action="A1", quote=made_up)

        analysis = build_analysis(
            _state(
                issues=[issue],
                relationship_signals=[signal(made_up)],
                client_signals=[],
                actions=[action],
                closed_actions=[closure],
            )
        )

        assert analysis.issues == []
        assert analysis.signals == []
        assert analysis.actions == []
        assert analysis.closed_action_ids == []
        assert analysis.quotes_rejected == 4

    def test_an_unknown_earlier_issue_id_makes_a_new_issue(self) -> None:
        issue = ISSUES.issues[0].model_copy(update={"earlier_issue": "I9"})

        analysis = build_analysis(_state(issues=[issue]))

        assert analysis.issues[0].earlier_issue_id is None

    def test_an_unknown_action_id_closes_nothing(self) -> None:
        closure = ClosedAction(action="A7", quote="Your laptop request is sorted now.")

        analysis = build_analysis(_state(closed_actions=[closure]))

        assert analysis.closed_action_ids == []
        assert analysis.quotes_rejected == 0


class TestCleaning:
    def test_the_same_quote_for_the_same_dimension_is_kept_once(self) -> None:
        quote = "To be honest I'm enjoying the team a lot."
        analysis = build_analysis(
            _state(
                relationship_signals=[signal(quote)],
                client_signals=[signal(quote)],
            )
        )

        assert len(analysis.signals) == 1

    def test_the_same_quote_for_another_dimension_is_kept(self) -> None:
        quote = "To be honest I'm enjoying the team a lot."
        analysis = build_analysis(
            _state(
                relationship_signals=[signal(quote)],
                client_signals=[signal(quote, dimension=Dimension.ENGAGEMENT)],
            )
        )

        assert len(analysis.signals) == 2

    @pytest.mark.parametrize("value", [-0.5, 1.7])
    def test_confidence_is_kept_within_zero_and_one(self, value: float) -> None:
        quote = "To be honest I'm enjoying the team a lot."
        analysis = build_analysis(
            _state(relationship_signals=[signal(quote, confidence=value)])
        )

        assert 0.0 <= analysis.signals[0].confidence <= 1.0

    @pytest.mark.parametrize("due_date", [None, "", "Friday", "2026-02-30"])
    def test_a_due_date_that_is_not_a_date_is_left_empty(
        self, due_date: str | None
    ) -> None:
        action = ExtractedAction.model_validate(
            {**ACTIONS.actions[0].model_dump(), "due_date": due_date}
        )

        analysis = build_analysis(_state(actions=[action]))

        assert analysis.actions[0].due_date is None

    def test_a_long_topic_is_cut_to_the_column(self) -> None:
        issue = ExtractedIssue.model_validate(
            {**ISSUES.issues[0].model_dump(), "topic": "x" * 900}
        )

        analysis = build_analysis(_state(issues=[issue]))

        assert len(analysis.issues[0].topic) == 500


ENJOYING = "To be honest I'm enjoying the team a lot."
STAGING = "I still can't get into the staging cluster."


class TestIndicators:
    def test_each_extraction_keeps_the_indicators_it_may_set(self) -> None:
        leaving = signal(ENJOYING, indicator=SignalIndicator.INTENT_TO_LEAVE)
        analysis = build_analysis(_state(relationship_signals=[leaving]))

        assert [(s.category, s.indicator) for s in analysis.signals] == [
            ("relationship_engagement", "intent_to_leave"),
            ("client", "client_dissatisfaction"),
        ]
        assert analysis.indicators_cleared == 0

    @pytest.mark.parametrize(
        ("node", "indicator"),
        [
            ("relationship_signals", SignalIndicator.CLIENT_DISSATISFACTION),
            ("relationship_signals", SignalIndicator.CONSULTANT_CHANGE_REQUESTED),
            ("client_signals", SignalIndicator.INTENT_TO_LEAVE),
        ],
    )
    def test_another_extraction_s_indicator_is_cleared_and_the_signal_kept(
        self, node: str, indicator: SignalIndicator
    ) -> None:
        changes: dict[str, Any] = {"relationship_signals": [], "client_signals": []}
        changes[node] = [signal(ENJOYING, indicator=indicator)]
        analysis = build_analysis(_state(**changes))

        [kept] = analysis.signals
        assert kept.indicator is None
        assert analysis.indicators_cleared == 1

    def test_a_duplicate_dropped_by_the_dedup_passes_its_indicator_on(self) -> None:
        analysis = build_analysis(
            _state(
                relationship_signals=[signal(ENJOYING)],
                client_signals=[
                    signal(ENJOYING, indicator=SignalIndicator.CLIENT_DISSATISFACTION)
                ],
            )
        )

        [kept] = analysis.signals
        assert kept.category == SignalCategory.RELATIONSHIP_ENGAGEMENT.value
        assert kept.indicator == "client_dissatisfaction"

    def test_an_issue_s_signal_takes_the_indicator_of_its_duplicate(self) -> None:
        duplicate = signal(
            STAGING,
            dimension=Dimension.TECHNICAL,
            polarity=Polarity.NEGATIVE,
            indicator=SignalIndicator.CLIENT_DISSATISFACTION,
        )
        analysis = build_analysis(
            _state(relationship_signals=[], client_signals=[duplicate])
        )

        assert analysis.issues[0].signal.indicator == "client_dissatisfaction"
        assert analysis.signals == []

    def test_an_indicator_whose_quote_is_not_found_is_dropped_with_it(self) -> None:
        missing = signal(
            "The client wants someone else.",
            indicator=SignalIndicator.CONSULTANT_CHANGE_REQUESTED,
        )
        analysis = build_analysis(
            _state(relationship_signals=[], client_signals=[missing])
        )

        assert analysis.signals == []
        assert analysis.quotes_rejected == 1

    def test_a_signal_without_an_indicator_has_none(self) -> None:
        analysis = build_analysis(_state())

        assert analysis.signals[0].indicator is None
        assert analysis.issues[0].signal.indicator is None


async def test_emit_signals_puts_the_analysis_in_the_state() -> None:
    update = await emit_signals(_state())

    assert update["analysis"].summary == "Priya is blocked on staging access."


def test_nothing_from_failed_nodes_gives_an_empty_analysis() -> None:
    analysis = build_analysis({"context": context()})

    assert analysis.summary is None
    assert analysis.issues == []
    assert analysis.signals == []
    assert analysis.actions == []
    assert analysis.quotes_rejected == 0
