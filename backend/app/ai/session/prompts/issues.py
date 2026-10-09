"""Prompt for issues: blockers and problems, linked to earlier ones."""

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

List the blockers and problems raised on the call that affect the \
consultant's work: technical blockers, missing access or equipment, unclear \
requirements, delivery problems. One item per distinct problem.

For each:
- topic: the problem in a few words.
- earlier_issue: if it is the same problem as one of the earlier issues \
listed (by id), that id; otherwise null. Match on the problem, not the \
wording.
- resolved_by_end: true only when the call says it is now solved.

{evidence_rules()}

Problems are usually negative; a problem reported as solved may be positive.

{QUOTE_RULES}

{SCOPE_RULES}

Return an empty list when no problem was raised."""


def build_user(context: SessionContext, transcript: str) -> str:
    if context.earlier_issues:
        earlier = "\n".join(
            f"- {i.ref}: {i.topic} ({i.status}; first raised "
            f"{i.first_seen.isoformat()}, raised {i.occurrence_count} time(s))"
            for i in context.earlier_issues
        )
    else:
        earlier = "None."
    return (
        f"People on this placement:\n{people_block(context)}\n\n"
        f"Earlier issues on this placement:\n{earlier}\n\n"
        f"Transcript:\n{transcript}"
    )
