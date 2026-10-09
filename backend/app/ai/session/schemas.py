"""What each session-pipeline node asks the model for (structured output).

These are the model's answers, not database rows: ``emit.py`` checks every
quote against the transcript and turns what survives into drafts, and the
analysis service stores them. Enumerated fields use the enumerations in
``app.models.enums``, so the JSON schema the model sees lists exactly the
stored values.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    Dimension,
    Polarity,
    SessionKind,
    SignalIndicator,
    SpeakerRole,
)

Severity = Literal[1, 2, 3]


class SpeakerAssignment(BaseModel):
    speaker: str = Field(description="The diarized speaker label, e.g. 'A'.")
    role: SpeakerRole = Field(description="Who this speaker is.")
    name: str | None = Field(
        default=None,
        description=(
            "The speaker's name when the transcript or the people listed make "
            "it clear; null otherwise."
        ),
    )


class RoleAttributionResult(BaseModel):
    speakers: list[SpeakerAssignment] = Field(
        description="One entry per speaker label in the transcript."
    )
    confidence: float = Field(description="0.0 (a guess) to 1.0 (certain).")
    rationale: str = Field(description="One sentence on the cues used.")


class ClassificationResult(BaseModel):
    session_class: SessionKind = Field(description="What kind of call this was.")
    project_phase: str = Field(
        description=(
            "Where the consultant is in the project, in a few words "
            "(e.g. 'second week, waiting for access')."
        )
    )


class SummaryResult(BaseModel):
    summary: str = Field(
        description="A factual summary of what was discussed, 4 to 8 sentences."
    )


class Evidence(BaseModel):
    """The fields every extracted signal carries."""

    dimension: Dimension = Field(description="The health dimension it bears on.")
    polarity: Polarity = Field(description="Good, bad or neutral for the placement.")
    severity: Severity = Field(description="How strongly it bears on the dimension.")
    confidence: float = Field(
        description="0.0 to 1.0: how sure you are that the quote shows this."
    )
    quote: str = Field(
        description=(
            "The exact words from the transcript, copied character for "
            "character, one or two sentences; no speaker label or timestamp."
        )
    )
    note: str = Field(description="One sentence: what this shows and why.")


class ExtractedIssue(Evidence):
    topic: str = Field(
        description="The blocker or problem in a few words, e.g. 'no VPN access'."
    )
    earlier_issue: str | None = Field(
        default=None,
        description=(
            "The id of the earlier issue (e.g. 'I2') this is the same as; null "
            "when it is new."
        ),
    )
    resolved_by_end: bool = Field(
        description="True when the call ended with it resolved."
    )


class IssuesResult(BaseModel):
    issues: list[ExtractedIssue] = Field(default_factory=list)


class ExtractedSignal(Evidence):
    indicator: SignalIndicator | None = Field(
        default=None,
        description=(
            "Set only when the quote says outright one of the indicators this "
            "prompt lists; null otherwise."
        ),
    )


class SignalsResult(BaseModel):
    signals: list[ExtractedSignal] = Field(default_factory=list)


class ExtractedAction(BaseModel):
    description: str = Field(description="What is to be done, in one sentence.")
    owner_role: SpeakerRole = Field(description="Who agreed to do it.")
    due_text: str | None = Field(
        default=None,
        description="The deadline as said, e.g. 'by Friday'; null if none was.",
    )
    due_date: str | None = Field(
        default=None,
        description=(
            "The deadline as YYYY-MM-DD, worked out from the call's date; null "
            "when none was said or it cannot be worked out."
        ),
    )
    quote: str = Field(
        description=(
            "The exact words where it was agreed, copied character for "
            "character; no speaker label or timestamp."
        )
    )


class ClosedAction(BaseModel):
    action: str = Field(description="The id of the earlier action, e.g. 'A1'.")
    quote: str = Field(
        description="The exact words saying it is done, copied character for character."
    )


class ActionsResult(BaseModel):
    actions: list[ExtractedAction] = Field(default_factory=list)
    closed: list[ClosedAction] = Field(
        default_factory=list,
        description="Earlier actions this call says are done.",
    )
