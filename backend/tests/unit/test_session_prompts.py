"""The prompts list every enumerated value from the one code constant."""

import pytest

from app.ai.session.prompts import (
    actions,
    classify,
    client_signals,
    issues,
    relationship_engagement,
    roles,
)
from app.ai.session.prompts.common import people_block, render_transcript, timestamp
from app.models.enums import (
    DIMENSION_MEANINGS,
    SESSION_KIND_MEANINGS,
    SEVERITY_MAX,
    SEVERITY_MEANINGS,
    SEVERITY_MIN,
    SPEAKER_ROLE_MEANINGS,
    Dimension,
    Polarity,
    SessionKind,
    SpeakerRole,
)
from tests.unit.session_pipeline_helpers import ROLES, context


def test_every_enumerated_value_has_a_meaning() -> None:
    assert set(DIMENSION_MEANINGS) == set(Dimension)
    assert set(SESSION_KIND_MEANINGS) == set(SessionKind)
    assert set(SPEAKER_ROLE_MEANINGS) == set(SpeakerRole)
    assert set(SEVERITY_MEANINGS) == set(range(SEVERITY_MIN, SEVERITY_MAX + 1))


@pytest.mark.parametrize(
    "system",
    [issues.SYSTEM, relationship_engagement.SYSTEM, client_signals.SYSTEM],
)
def test_signal_prompts_list_every_dimension_polarity_and_severity(
    system: str,
) -> None:
    for dimension in Dimension:
        assert f"- {dimension.value}: {DIMENSION_MEANINGS[dimension]}" in system
    for polarity in Polarity:
        assert polarity.value in system
    for level, meaning in SEVERITY_MEANINGS.items():
        assert f"- {level}: {meaning}" in system


@pytest.mark.parametrize("system", [roles.SYSTEM, actions.SYSTEM])
def test_role_prompts_list_every_role(system: str) -> None:
    for role, meaning in SPEAKER_ROLE_MEANINGS.items():
        assert f"- {role.value}: {meaning}" in system


def test_classify_lists_every_session_kind() -> None:
    for kind, meaning in SESSION_KIND_MEANINGS.items():
        assert f"- {kind.value}: {meaning}" in classify.SYSTEM


def test_transcript_lines_carry_time_and_speaker_then_role() -> None:
    plain = render_transcript(context())
    with_roles = render_transcript(context(), ROLES.speakers)

    assert plain.splitlines()[1].startswith("[0:05] Speaker B: I still can't")
    assert with_roles.splitlines()[1].startswith(
        "[0:05] Speaker B (consultant, Priya Shah): I still can't"
    )


def test_a_transcript_without_utterances_is_its_full_text() -> None:
    assert render_transcript(context(utterances=[], full_text="Hello.")) == "Hello."


@pytest.mark.parametrize(
    ("ms", "text"), [(0, "0:00"), (65_400, "1:05"), (3_725_000, "1:02:05")]
)
def test_timestamps(ms: int, text: str) -> None:
    assert timestamp(ms) == text


def test_people_block_names_the_placement_and_the_call_day() -> None:
    block = people_block(context())

    assert "Consultant: Priya Shah" in block
    assert "Client: Acme; project: Data platform" in block
    assert "Client manager: Dana Lee" in block
    assert "PMO SME (sme): Sam Okafor" in block
    assert "Placement specialist" not in block
    assert "Call held on 2026-10-06 (Tuesday)" in block
