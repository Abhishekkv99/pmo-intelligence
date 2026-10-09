"""emit_signals: the deterministic last node of the session pipeline.

Turns the nodes' answers into drafts to store. Every quote (issue, signal,
action, closed action) must be found in the transcript; an item whose quote
is not found is dropped and counted in ``quotes_rejected``, never stored.
A found quote gives the item its speaker's role and its moment in the
recording. An issue or action id the model made up is treated as absent.
The same quote read twice for the same dimension (two nodes can both see
it) is kept once.
"""

import logging
import uuid
from datetime import date
from typing import Any

from app.ai.session.drafts import (
    ActionDraft,
    IssueDraft,
    SessionAnalysis,
    SignalDraft,
)
from app.ai.session.schemas import Evidence, SpeakerAssignment
from app.ai.session.state import SessionGraphState
from app.models.enums import SignalCategory
from app.services.quote_check import QuoteMatch, TranscriptIndex, normalise

logger = logging.getLogger(__name__)

TOPIC_LIMIT = 500
SHORT_TEXT_LIMIT = 255


def _due_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


class _Emitter:
    def __init__(self, state: SessionGraphState) -> None:
        context = state["context"]
        self.index = TranscriptIndex(context.utterances, context.full_text)
        self.roles: dict[str, SpeakerAssignment] = {
            s.speaker: s for s in state.get("speakers", [])
        }
        self.rejected = 0
        self._seen: set[tuple[str, str]] = set()

    def place(self, quote: str) -> QuoteMatch | None:
        match = self.index.find(quote)
        if match is None:
            self.rejected += 1
        return match

    def role_of(self, match: QuoteMatch) -> str | None:
        assignment = self.roles.get(match.speaker) if match.speaker else None
        return assignment.role.value if assignment else None

    def signal(self, category: SignalCategory, item: Evidence) -> SignalDraft | None:
        match = self.place(item.quote)
        if match is None:
            return None
        key = (normalise(item.quote), item.dimension.value)
        if key in self._seen:
            return None
        self._seen.add(key)
        return SignalDraft(
            category=category.value,
            dimension=item.dimension.value,
            polarity=item.polarity.value,
            severity=int(item.severity),
            confidence=_clamp(item.confidence),
            quote=item.quote.strip(),
            note=item.note.strip() or None,
            speaker_role=self.role_of(match),
            offset_ms=match.offset_ms,
        )


def build_analysis(state: SessionGraphState) -> SessionAnalysis:
    context = state["context"]
    emitter = _Emitter(state)
    earlier_issues = {i.ref: i.issue_id for i in context.earlier_issues}
    open_actions = {a.ref: a.action_id for a in context.open_actions}

    issues: list[IssueDraft] = []
    for item in state.get("issues", []):
        signal = emitter.signal(SignalCategory.ISSUE, item)
        if signal is None:
            continue
        issues.append(
            IssueDraft(
                topic=item.topic.strip()[:TOPIC_LIMIT],
                earlier_issue_id=earlier_issues.get(item.earlier_issue or ""),
                resolved_by_end=item.resolved_by_end,
                signal=signal,
            )
        )

    signals: list[SignalDraft] = []
    for category, items in (
        (SignalCategory.RELATIONSHIP_ENGAGEMENT, state.get("relationship_signals", [])),
        (SignalCategory.CLIENT, state.get("client_signals", [])),
    ):
        for evidence in items:
            drafted = emitter.signal(category, evidence)
            if drafted is not None:
                signals.append(drafted)

    actions: list[ActionDraft] = []
    for action in state.get("actions", []):
        match = emitter.place(action.quote)
        if match is None:
            continue
        due_text = (action.due_text or "").strip()[:SHORT_TEXT_LIMIT] or None
        actions.append(
            ActionDraft(
                description=action.description.strip(),
                owner_role=action.owner_role.value,
                due_text=due_text,
                due_date=_due_date(action.due_date),
                quote=action.quote.strip(),
                offset_ms=match.offset_ms,
            )
        )

    closed: list[uuid.UUID] = []
    for closure in state.get("closed_actions", []):
        action_id = open_actions.get(closure.action)
        if action_id is None or action_id in closed:
            continue
        if emitter.place(closure.quote) is not None:
            closed.append(action_id)

    phase = state.get("project_phase")
    return SessionAnalysis(
        speaker_roles={
            s.speaker: {"role": s.role.value, "name": s.name}
            for s in state.get("speakers", [])
        },
        session_class=state.get("session_class"),
        project_phase=phase.strip()[:SHORT_TEXT_LIMIT] if phase else None,
        summary=state.get("summary"),
        issues=issues,
        signals=signals,
        actions=actions,
        closed_action_ids=closed,
        quotes_rejected=emitter.rejected,
    )


async def emit_signals(state: SessionGraphState) -> dict[str, Any]:
    analysis = build_analysis(state)
    if analysis.quotes_rejected:
        logger.info(
            "Session pipeline dropped %d item(s) whose quote was not in the transcript",
            analysis.quotes_rejected,
        )
    return {"analysis": analysis}
