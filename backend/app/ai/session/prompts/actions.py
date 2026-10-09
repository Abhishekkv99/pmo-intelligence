"""Prompt for actions: what was agreed, and earlier actions now done."""

from app.ai.session.prompts.common import (
    CALL_INTRO,
    QUOTE_RULES,
    bullet_list,
    people_block,
)
from app.ai.session.state import SessionContext
from app.models.enums import SPEAKER_ROLE_MEANINGS

SYSTEM = f"""\
{CALL_INTRO}

1. List the actions agreed on the call: something a person said they or \
someone else will do after the call. Not things already done, not general \
advice.
For each:
- description: what is to be done, in one sentence.
- owner_role: who will do it, one of:
{bullet_list(SPEAKER_ROLE_MEANINGS, "  ")}
- due_text: the deadline as said ("by Friday"), or null.
- due_date: that deadline as YYYY-MM-DD, worked out from the date the call \
was held; null when no deadline was said or it cannot be worked out.
- quote: the words where it was agreed.

2. In closed, list the earlier open actions (by id) that the call says are \
done, each with the quote that says so.

{QUOTE_RULES}

Return empty lists when nothing was agreed or closed."""


def build_user(context: SessionContext, transcript: str) -> str:
    if context.open_actions:
        earlier = "\n".join(
            f"- {a.ref}: {a.description} (owner {a.owner_role}"
            + (f", due {a.due_text}" if a.due_text else "")
            + ")"
            for a in context.open_actions
        )
    else:
        earlier = "None."
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Earlier open actions on this placement:\n{earlier}\n\n"
        f"Transcript:\n{transcript}"
    )
