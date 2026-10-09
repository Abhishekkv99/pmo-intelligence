"""Text shared by the session pipeline's prompts.

The enumerated values and their meanings come from ``app.models.enums``
(``SPEAKER_ROLE_MEANINGS``, ``SESSION_KIND_MEANINGS``, ``DIMENSION_MEANINGS``,
``SEVERITY_MEANINGS``, ``SIGNAL_INDICATOR_MEANINGS`` with
``SIGNAL_INDICATORS_BY_CATEGORY``, ``Polarity``); the prompts list them from
there and never repeat them by hand.
"""

from collections.abc import Mapping

from app.ai.session.schemas import SpeakerAssignment
from app.ai.session.state import SessionContext
from app.models.enums import (
    DIMENSION_MEANINGS,
    SEVERITY_MEANINGS,
    SIGNAL_INDICATOR_MEANINGS,
    SIGNAL_INDICATORS_BY_CATEGORY,
    Polarity,
    SignalCategory,
    SpeakerRole,
)

CALL_INTRO = """\
You are reading the transcript of a recorded PMO call at an IT consultancy. \
The consultancy places consultants (contractors) with client companies. On \
the call, a consultant talks with PMO staff: a PMO manager, a PMO \
subject-matter expert (SME), a tech lead or a placement specialist (PS). \
The PMO uses what you extract to see early when a placement is at risk; a \
person reviews everything, and nothing is decided from it automatically."""

QUOTE_RULES = """\
Quotes:
- Copy the quote character for character from the transcript text: one or \
two consecutive sentences, spoken by one speaker.
- Never paraphrase, correct, shorten with "...", or join words that are not \
next to each other. Leave out the timestamp and the speaker label.
- An item you cannot support with such a quote must be left out. An item \
whose quote is not found in the transcript is discarded."""

SCOPE_RULES = """\
Report only what bears on the consultant's placement: their work, the \
client, the team and how they are doing in the role. Leave out anything \
about anyone's private life that does not."""


def bullet_list[KeyT](meanings: Mapping[KeyT, str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {key}: {text}" for key, text in meanings.items())


def evidence_rules() -> str:
    polarities = ", ".join(p.value for p in Polarity)
    return (
        "Every item carries:\n"
        f"- dimension, one of:\n{bullet_list(DIMENSION_MEANINGS, '  ')}\n"
        f"- polarity: {polarities} (for the placement's health)\n"
        f"- severity:\n{bullet_list(SEVERITY_MEANINGS, '  ')}\n"
        "- confidence: 0.0 to 1.0, how sure you are that the quote shows this\n"
        "- quote: see the quote rules\n"
        "- note: one sentence on what it shows and why"
    )


def indicator_rules(category: SignalCategory) -> str:
    """The indicators one extraction may set, with their meanings."""
    allowed = {
        indicator: SIGNAL_INDICATOR_MEANINGS[indicator]
        for indicator in SIGNAL_INDICATORS_BY_CATEGORY[category]
    }
    return (
        "- indicator: set it only when the quote says outright one of these, "
        "and leave it null for every other item:\n"
        f"{bullet_list(allowed, '  ')}"
    )


def timestamp(ms: object) -> str:
    total = int(ms) // 1000 if isinstance(ms, int | float) else 0
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def render_transcript(
    context: SessionContext, speakers: list[SpeakerAssignment] | None = None
) -> str:
    """The transcript, one utterance per line, with roles once they are known."""
    if not context.utterances:
        return context.full_text
    known = {s.speaker: s for s in speakers or []}
    lines = []
    for utterance in context.utterances:
        label = str(utterance.get("speaker") or "?")
        tag = f"Speaker {label}"
        speaker = known.get(label)
        if speaker is not None:
            who = speaker.role.value
            if speaker.name:
                who += f", {speaker.name}"
            tag += f" ({who})"
        stamp = timestamp(utterance.get("start_ms"))
        lines.append(f"[{stamp}] {tag}: {utterance.get('text') or ''}")
    return "\n".join(lines)


def people_block(context: SessionContext) -> str:
    lines = [
        f"Consultant: {context.consultant_name}",
        f"Client: {context.client_name}; project: {context.project_name}",
    ]
    if context.client_manager_name:
        lines.append(f"Client manager: {context.client_manager_name}")
    labels = {
        SpeakerRole.PS: "Placement specialist (ps)",
        SpeakerRole.SME: "PMO SME (sme)",
        SpeakerRole.TECH_LEAD: "Tech lead (tech_lead)",
    }
    for role, label in labels.items():
        if role in context.people:
            lines.append(f"{label}: {context.people[role]}")
    lines.append(
        f"Call held on {context.call_day.isoformat()} "
        f"({context.call_day.strftime('%A')})"
    )
    return "\n".join(lines)
