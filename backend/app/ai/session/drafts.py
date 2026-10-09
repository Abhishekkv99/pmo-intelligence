"""What the session pipeline hands the analysis service to store.

Built by ``emit_signals`` from the nodes' answers, after every quote was
found in the transcript. Plain data: no database ids beyond the earlier
issues and actions the nodes were offered.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SignalDraft:
    category: str
    dimension: str
    polarity: str
    severity: int
    confidence: float
    quote: str
    note: str | None
    speaker_role: str | None
    offset_ms: int | None
    # A ``SignalIndicator`` the quote states outright, for the critical triggers.
    indicator: str | None = None


@dataclass(frozen=True)
class IssueDraft:
    topic: str
    # The earlier issue it is the same as; ``None`` for a new one.
    earlier_issue_id: uuid.UUID | None
    resolved_by_end: bool
    signal: SignalDraft


@dataclass(frozen=True)
class ActionDraft:
    description: str
    owner_role: str
    due_text: str | None
    due_date: date | None
    quote: str
    offset_ms: int | None


@dataclass(frozen=True)
class SessionAnalysis:
    # Speaker label → {"role", "name"}.
    speaker_roles: dict[str, dict[str, str | None]] = field(default_factory=dict)
    session_class: str | None = None
    project_phase: str | None = None
    summary: str | None = None
    issues: list[IssueDraft] = field(default_factory=list)
    signals: list[SignalDraft] = field(default_factory=list)
    actions: list[ActionDraft] = field(default_factory=list)
    closed_action_ids: list[uuid.UUID] = field(default_factory=list)
    # Items dropped because their quote was not in the transcript.
    quotes_rejected: int = 0
    # Indicators dropped because their extraction may not set them.
    indicators_cleared: int = 0
