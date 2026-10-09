"""Prompt for attribute_roles: which diarized speaker is who."""

from app.ai.session.prompts.common import CALL_INTRO, bullet_list, people_block
from app.ai.session.state import SessionContext
from app.models.enums import SPEAKER_ROLE_MEANINGS

SYSTEM = f"""\
{CALL_INTRO}

The transcript is diarized with anonymous speaker labels (A, B, ...). Decide \
who each label is. Roles:
{bullet_list(SPEAKER_ROLE_MEANINGS)}

Rules:
- Give every label in the transcript exactly one role.
- A call is about one consultant, so normally one label is the consultant. \
Two labels may share any other role.
- Use the people listed, names said on the call and what each speaker does \
(who asks for help, who gives it, who reports progress) as cues.
- Give a name only when the transcript or the people listed make it clear.
- Use other when a speaker's role is unclear; never guess a named person.
- Set confidence honestly: lower for short or one-sided calls."""


def build_user(context: SessionContext, transcript: str) -> str:
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Transcript:\n{transcript}"
    )
