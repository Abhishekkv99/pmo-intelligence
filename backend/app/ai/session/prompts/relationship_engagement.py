"""Prompt for relationship_engagement: the team, the manager, morale."""

from app.ai.session.prompts.common import (
    CALL_INTRO,
    QUOTE_RULES,
    SCOPE_RULES,
    evidence_rules,
    people_block,
)
from app.ai.session.state import SessionContext

SYSTEM = f"""\
{CALL_INTRO}

List what the call shows about:
- the consultant's relationship with the client's team, their manager and \
superiors: how they describe them, conflict, being left out, support, \
friction others mention (usually relationship);
- the consultant's morale, confidence, stress, enthusiasm and intent to stay, \
including any talk of leaving, another offer or not wanting to continue \
(usually engagement);
- how visible they are: updates, questions, stand-ups (communication).

Positive signals matter as much as negative ones. One item per distinct \
point.

{evidence_rules()}

{QUOTE_RULES}

{SCOPE_RULES}

Return an empty list when the call shows none of this."""


def build_user(context: SessionContext, transcript: str) -> str:
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Transcript:\n{transcript}"
    )
