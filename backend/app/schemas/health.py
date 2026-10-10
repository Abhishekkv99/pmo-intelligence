"""The risk board and a placement's health page.

One model per route for every reader, marked with ``view``. In the
``technical`` view (an SME) the overall, the RAG level, the overall's trend,
the flags and the five other dimensions are null or empty, and only Technical
evidence is listed; the Technical score and its own trend are always given.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import (
    Dimension,
    ExtensionStatus,
    FlagSeverity,
    HealthView,
    IssueStatus,
    PlacementStatus,
    Polarity,
    RiskLevel,
    RiskTrigger,
    SessionKind,
    SessionStatus,
    SignalIndicator,
    SnapshotReason,
    SourceKind,
    SpeakerRole,
    Trend,
)
from app.schemas.sessions import ActionView, NamedRef, PersonView


class FlagSummary(BaseModel):
    id: uuid.UUID
    trigger: RiskTrigger
    severity: FlagSeverity
    opened_at: datetime


class NextAction(BaseModel):
    id: uuid.UUID
    description: str
    owner_role: SpeakerRole
    due_date: date


class RiskBoardRow(BaseModel):
    """One active placement on the board, as of its latest snapshot."""

    placement_id: uuid.UUID
    view: HealthView
    consultant: NamedRef
    client: NamedRef
    project: NamedRef
    # For the board's filters.
    ps: PersonView | None
    tech_lead: PersonView | None
    start_date: date
    weeks_in: int
    # False when there is no snapshot yet, or no signal in the lookback.
    scored: bool
    computed_at: datetime | None
    # Null in the technical view.
    overall: float | None
    risk_level: RiskLevel | None
    trend: Trend | None
    trend_delta: float | None
    technical: float | None
    technical_trend: Trend | None
    technical_trend_delta: float | None
    # Empty in the technical view.
    open_flags: list[FlagSummary]
    # The latest completed call; UK days since it.
    last_call_at: datetime | None
    days_since_last_call: int | None
    next_action: NextAction | None


class DimensionScores(BaseModel):
    """The six scores; in the technical view only ``technical`` is set."""

    delivery: float | None
    technical: float | None
    relationship: float | None
    engagement: float | None
    onboarding: float | None
    communication: float | None


class EvidenceSignal(BaseModel):
    """A signal shown as evidence, with where it was said."""

    id: uuid.UUID
    source_kind: SourceKind
    source_id: uuid.UUID
    dimension: Dimension
    polarity: Polarity
    severity: int
    confidence: float
    quote: str
    note: str | None
    speaker_role: SpeakerRole | None
    occurred_at: datetime
    offset_ms: int | None
    indicator: SignalIndicator | None


class Contributor(BaseModel):
    signal: EvidenceSignal
    weight: float
    value: float


class DimensionEvidence(BaseModel):
    dimension: Dimension
    signal_count: int
    # The signals that pulled the score furthest from the prior, largest first.
    contributors: list[Contributor]


class SnapshotDetail(BaseModel):
    computed_at: datetime
    reason: SnapshotReason
    scored: bool
    scores: DimensionScores
    overall: float | None
    risk_level: RiskLevel | None
    trend: Trend | None
    trend_delta: float | None
    technical_trend: Trend | None
    technical_trend_delta: float | None
    # Null in the technical view; each dimension's count is in its evidence.
    signal_count: int | None
    weights_version: str
    evidence: list[DimensionEvidence]


class SnapshotPoint(BaseModel):
    """One point of the health chart."""

    computed_at: datetime
    reason: SnapshotReason
    scored: bool
    scores: DimensionScores
    overall: float | None
    risk_level: RiskLevel | None
    trend: Trend | None
    technical_trend: Trend | None


class FlagDetail(BaseModel):
    id: uuid.UUID
    trigger: RiskTrigger
    severity: FlagSeverity
    opened_at: datetime
    evidence: list[EvidenceSignal]


class PlacementSession(BaseModel):
    """A call of the placement; a completed one is a marker on the chart."""

    id: uuid.UUID
    held_at: datetime
    kind: SessionKind | None
    status: SessionStatus
    duration_seconds: float | None
    # Technical signals only in the technical view.
    signal_count: int
    action_count: int


class OpenIssue(BaseModel):
    id: uuid.UUID
    topic: str
    status: IssueStatus
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class PlacementAction(ActionView):
    """An action with the call or message it was agreed in."""

    source_kind: SourceKind
    source_id: uuid.UUID


class RegisterFields(BaseModel):
    start_date: date
    expected_end_date: date | None
    status: PlacementStatus
    client_manager_name: str | None
    ps: PersonView | None
    sme: PersonView | None
    tech_lead: PersonView | None
    # Null in the technical view: contract matters.
    extension_status: ExtensionStatus | None
    rate_band: str | None
    ended_reason: str | None


class OtherPlacement(BaseModel):
    """Another placement of the same consultant that the reader may see."""

    id: uuid.UUID
    client: NamedRef
    project: NamedRef
    start_date: date
    expected_end_date: date | None
    status: PlacementStatus


class RagThresholds(BaseModel):
    """The RAG thresholds of the health configuration in use.

    The page draws its bands and colours from these, never from constants of
    its own, so a configuration change never leaves the page wrong.
    """

    green_from: float
    amber_from: float


class PlacementHealth(BaseModel):
    """The placement (consultant) page."""

    placement_id: uuid.UUID
    view: HealthView
    consultant: NamedRef
    client: NamedRef
    project: NamedRef
    weeks_in: int
    register_fields: RegisterFields
    latest: SnapshotDetail | None
    # Every snapshot, oldest first.
    history: list[SnapshotPoint]
    # Empty in the technical view.
    open_flags: list[FlagDetail]
    # Newest call first.
    sessions: list[PlacementSession]
    open_issues: list[OpenIssue]
    actions: list[PlacementAction]
    other_placements: list[OtherPlacement]
    thresholds: RagThresholds
