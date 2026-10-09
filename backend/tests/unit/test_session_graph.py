"""The session pipeline end to end, with the model mocked node by node."""

import pytest

from app.ai.session import nodes
from app.ai.session.graph import run_session_pipeline
from tests.unit.session_pipeline_helpers import (
    ANSWERS,
    OPEN_ACTION_ID,
    SUMMARY,
    FakeModel,
    context,
)


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    fake = FakeModel()
    monkeypatch.setattr(nodes, "invoke_structured", fake)
    return fake


async def test_every_node_runs_and_emit_builds_the_analysis(model: FakeModel) -> None:
    result = await run_session_pipeline(context())

    assert sorted(result.succeeded) == sorted(name for name, _ in ANSWERS.values())
    assert result.node_errors == []
    assert result.usable
    assert len(result.cost_records) == 7
    analysis = result.analysis
    assert analysis.summary == SUMMARY.summary
    assert analysis.session_class == "check_in"
    assert len(analysis.issues) == 1
    assert len(analysis.signals) == 2
    assert len(analysis.actions) == 1
    assert analysis.closed_action_ids == [OPEN_ACTION_ID]


async def test_nodes_after_role_attribution_read_the_roles(model: FakeModel) -> None:
    await run_session_pipeline(context())

    assert "Speaker B (consultant, Priya Shah):" in model.prompts["summarise"]
    assert "Speaker B (consultant" not in model.prompts["attribute_roles"]


async def test_earlier_issues_and_open_actions_are_offered_by_id(
    model: FakeModel,
) -> None:
    await run_session_pipeline(context())

    assert "- I1: no staging access (open;" in model.prompts["issues"]
    assert "- A1: Order a laptop (owner sme)" in model.prompts["actions"]


async def test_a_failing_node_is_recorded_and_the_rest_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nodes, "invoke_structured", FakeModel({"issues", "classify"}))

    result = await run_session_pipeline(context())

    assert {e["node"] for e in result.node_errors} == {"issues", "classify"}
    assert result.usable
    assert result.analysis.issues == []
    assert result.analysis.session_class is None
    assert len(result.analysis.signals) == 2
    assert len(result.cost_records) == 5


async def test_role_attribution_failing_leaves_signals_without_a_speaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nodes, "invoke_structured", FakeModel({"attribute_roles"}))

    result = await run_session_pipeline(context())

    assert result.usable
    assert all(s.speaker_role is None for s in result.analysis.signals)


async def test_summary_and_every_extraction_failing_is_not_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = {
        "summarise",
        "issues",
        "relationship_engagement",
        "client_signals",
        "actions",
    }
    monkeypatch.setattr(nodes, "invoke_structured", FakeModel(failing))

    result = await run_session_pipeline(context())

    assert not result.usable
    assert sorted(result.succeeded) == ["attribute_roles", "classify"]
    assert len(result.node_errors) == 5
