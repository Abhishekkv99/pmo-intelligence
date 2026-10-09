"""Prompt for client_signals: what is said about the client's view."""

from app.ai.session.prompts.common import (
    CALL_INTRO,
    QUOTE_RULES,
    SCOPE_RULES,
    evidence_rules,
    indicator_rules,
    people_block,
)
from app.ai.session.state import SessionContext
from app.models.enums import SignalCategory

SYSTEM = f"""\
{CALL_INTRO}

List what is said on the call about the client's view of the consultant and \
their work: what the client expects, has praised, has complained about or \
escalated, or asked to change, including a request for a different \
consultant. Usually delivery or relationship. One item per distinct point.

A report that the client manager is unhappy, has escalated, or asked for a \
change of consultant is severity 3.

{evidence_rules()}
{indicator_rules(SignalCategory.CLIENT)}

{QUOTE_RULES}

{SCOPE_RULES}

Return an empty list when nothing is said about the client's view."""


def build_user(context: SessionContext, transcript: str) -> str:
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Transcript:\n{transcript}"
    )
