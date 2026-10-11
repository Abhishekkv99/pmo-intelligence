"""The session pipeline's input and the state passed between its nodes.

The graph touches no database: the analysis service loads a
``SessionContext`` (the transcript, the register's names and the
placement's earlier issues and actions) and stores what the graph returns.
Costs, node errors and the names of the nodes that succeeded are merged
across the parallel nodes with ``operator.add``.
"""

import operator
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, TypedDict

from app.ai.session.drafts import SessionAnalysis
from app.ai.session.schemas import (
    ClosedAction,
    ExtractedAction,
    ExtractedIssue,
    ExtractedSignal,
    SpeakerAssignment,
)
from app.models.enums import SpeakerRole


@dataclass(frozen=True)
class IssueRef:
    """An earlier issue offered to the issues node by a short id."""

    ref: str
    issue_id: uuid.UUID
    topic: str
    status: str
    first_seen: date
    occurrence_count: int


@dataclass(frozen=True)
class ActionRef:
    """An earlier open action offered to the actions node by a short id."""

    ref: str
    action_id: uuid.UUID
    description: str
    owner_role: str
    due_text: str | None


@dataclass(frozen=True)
class SessionContext:
    held_at: datetime
    # The call's date where it was held (UK), for working out due dates.
    call_day: date
    consultant_name: str
    client_name: str
    project_name: str
    client_manager_name: str | None
    # The placement's named people: PS, SME and the consultant's CDM, when named.
    people: dict[SpeakerRole, str]
    # Each ``{"speaker", "text", "start_ms", "end_ms", "confidence"}``.
    utterances: list[dict[str, Any]]
    full_text: str
    earlier_issues: list[IssueRef] = field(default_factory=list)
    open_actions: list[ActionRef] = field(default_factory=list)


class SessionGraphState(TypedDict, total=False):
    context: SessionContext

    speakers: list[SpeakerAssignment]
    session_class: str
    project_phase: str
    summary: str
    issues: list[ExtractedIssue]
    relationship_signals: list[ExtractedSignal]
    client_signals: list[ExtractedSignal]
    actions: list[ExtractedAction]
    closed_actions: list[ClosedAction]

    # Set by emit_signals: what survived the quote check, ready to store.
    analysis: SessionAnalysis

    cost_records: Annotated[list[dict[str, Any]], operator.add]
    node_errors: Annotated[list[dict[str, Any]], operator.add]
    succeeded: Annotated[list[str], operator.add]
