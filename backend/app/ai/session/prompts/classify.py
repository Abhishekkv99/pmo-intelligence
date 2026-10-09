"""Prompt for classify: what kind of call, and where the consultant is."""

from app.ai.session.prompts.common import CALL_INTRO, bullet_list, people_block
from app.ai.session.state import SessionContext
from app.models.enums import SESSION_KIND_MEANINGS

SYSTEM = f"""\
{CALL_INTRO}

Classify the call as one of:
{bullet_list(SESSION_KIND_MEANINGS)}

Choose the kind that describes most of the call; escalation whenever a \
problem with the client or the placement needs someone to step in.

Also say where the consultant is in the project, in a few words (for \
example "second week, still waiting for access" or "six months in, steady \
delivery")."""


def build_user(context: SessionContext, transcript: str) -> str:
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Transcript:\n{transcript}"
    )
