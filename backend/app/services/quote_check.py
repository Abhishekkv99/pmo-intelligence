"""Evidence quotes checked against the transcript they claim to come from.

A signal or an action is stored only when its quote is found in the source
(docs/PRD.md, "Keep the model honest"). The check is a substring match after
normalising both sides the same way: Unicode NFKC, case folded, curly quotes
and dashes made plain, whitespace collapsed. The quote's own leading and
trailing quote marks, spaces and punctuation are ignored, since a model often
adds or trims them; nothing inside the quote is.

A match is placed in the utterance where it starts, which gives the speaker
label and the moment in the recording (the utterance's start).
"""

import bisect
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_PLAIN = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
    }
)
_SPACE = re.compile(r"\s+")
# Stripped from the ends of a quote only.
_EDGE = " \"'.,;:!?-()[]"


def normalise(text: str) -> str:
    """The form both a quote and its transcript are compared in."""
    folded = unicodedata.normalize("NFKC", text).casefold().translate(_PLAIN)
    return _SPACE.sub(" ", folded).strip()


@dataclass(frozen=True)
class QuoteMatch:
    """Where a quote was found. ``speaker`` and ``offset_ms`` are ``None``
    when the transcript has no utterances to place it in."""

    utterance_index: int | None
    speaker: str | None
    offset_ms: int | None


class TranscriptIndex:
    """A transcript prepared once for checking many quotes."""

    def __init__(self, utterances: Sequence[dict[str, Any]], full_text: str | None):
        self._utterances = list(utterances)
        parts: list[str] = []
        self._starts: list[int] = []
        position = 0
        for utterance in self._utterances:
            text = normalise(str(utterance.get("text") or ""))
            self._starts.append(position)
            parts.append(text)
            position += len(text) + 1
        if parts:
            self._text = " ".join(parts)
        else:
            self._text = normalise(full_text or "")

    def find(self, quote: str) -> QuoteMatch | None:
        """Where ``quote`` occurs (its first occurrence), or ``None``."""
        needle = normalise(quote).strip(_EDGE)
        if not needle:
            return None
        at = self._text.find(needle)
        if at < 0:
            return None
        if not self._utterances:
            return QuoteMatch(utterance_index=None, speaker=None, offset_ms=None)
        index = bisect.bisect_right(self._starts, at) - 1
        utterance = self._utterances[index]
        start = utterance.get("start_ms")
        return QuoteMatch(
            utterance_index=index,
            speaker=None
            if utterance.get("speaker") is None
            else str(utterance["speaker"]),
            offset_ms=int(start) if start is not None else None,
        )
