"""The sessions list and the session page."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import (
    ActionStatus,
    Dimension,
    IssueStatus,
    Polarity,
    SessionKind,
    SessionSource,
    SessionStatus,
    SignalCategory,
    SpeakerRole,
)


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class SessionListItem(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    consultant: NamedRef
    client: NamedRef
    project: NamedRef
    held_at: datetime
    duration_seconds: float | None
    kind: SessionKind | None
    status: SessionStatus
    error_message: str | None
    signal_count: int
    action_count: int


class SpeakerView(BaseModel):
    """Who a diarized label was: a role, and a name when the call gave one."""

    role: SpeakerRole
    name: str | None


class UtteranceView(BaseModel):
    speaker: str
    text: str
    start_ms: int
    end_ms: int


class SignalView(BaseModel):
    id: uuid.UUID
    category: SignalCategory
    dimension: Dimension
    polarity: Polarity
    severity: int
    confidence: float
    quote: str
    note: str | None
    speaker_role: SpeakerRole | None
    offset_ms: int | None
    issue_id: uuid.UUID | None


class IssueView(BaseModel):
    """An issue this call raised or saw again, as it stands now."""

    id: uuid.UUID
    topic: str
    status: IssueStatus
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    # Where this call talks about it.
    offset_ms: int | None


class PersonView(BaseModel):
    id: uuid.UUID
    full_name: str | None
    email: str


class ActionView(BaseModel):
    id: uuid.UUID
    description: str
    owner_role: SpeakerRole
    owner: PersonView | None
    quote: str
    offset_ms: int | None
    due_text: str | None
    due_date: date | None
    status: ActionStatus
    closed_at: datetime | None


class SessionCost(BaseModel):
    transcription_usd: float
    analysis_usd: float
    total_usd: float


class SessionDetail(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    consultant: NamedRef
    client: NamedRef
    project: NamedRef
    held_at: datetime
    duration_seconds: float | None
    kind: SessionKind | None
    kind_overridden: bool
    # What the pipeline classified the call as, whatever the kind in use.
    session_class: SessionKind | None
    project_phase: str | None
    source: SessionSource
    original_filename: str | None
    status: SessionStatus
    error_message: str | None
    quotes_rejected: int
    has_recording: bool
    summary: str | None
    speakers: dict[str, SpeakerView]
    utterances: list[UtteranceView]
    signals: list[SignalView]
    issues: list[IssueView]
    actions: list[ActionView]
    # Earlier actions this call said were done.
    closed_actions: list[ActionView]
    cost: SessionCost
    # For the global roles only; null for everyone else.
    node_errors: list[dict[str, object]] | None


class MediaUrl(BaseModel):
    url: str
    content_type: str
    expires_in_seconds: int


class KindUpdate(BaseModel):
    kind: SessionKind
