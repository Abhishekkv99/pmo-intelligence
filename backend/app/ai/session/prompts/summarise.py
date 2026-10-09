"""Prompt for summarise: a factual summary of the call."""

from app.ai.session.prompts.common import CALL_INTRO, SCOPE_RULES, people_block
from app.ai.session.state import SessionContext

SYSTEM = f"""\
{CALL_INTRO}

Write a factual summary of the call in 4 to 8 plain sentences, for a PMO \
reader who was not on it: what the consultant is working on, the problems \
raised, how the consultant described the team, the client and their own \
situation, and what was agreed.

Rules:
- Say only what the transcript says; no opinions, no advice, no scores.
- Refer to people by name or role as the transcript does.
- {SCOPE_RULES}"""


def build_user(context: SessionContext, transcript: str) -> str:
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Transcript:\n{transcript}"
    )
