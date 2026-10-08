"""Tie a recordings folder to a consultant by the names in the folder name.

A consultant is a candidate when the folder name holds their first or last
name as a whole word, ignoring case and accents: "Ann" does not match
"Anna". The first and last tokens of ``full_name`` are used, so a middle name
never matches. Every consultant in the register counts, ``left`` included,
because old recordings belong to past placements.

One candidate is a match. Several are resolved only when exactly one of them
has both first and last name in the folder name; otherwise a person chooses.
"""

import uuid
from dataclasses import dataclass, field

from app.models.enums import FolderMatchStatus
from app.services.recordings.folder_names import fold


@dataclass(frozen=True)
class ConsultantName:
    id: uuid.UUID
    full_name: str


@dataclass(frozen=True)
class FolderMatch:
    status: FolderMatchStatus
    consultant_id: uuid.UUID | None = None
    candidate_ids: list[uuid.UUID] = field(default_factory=list)


def name_tokens(full_name: str) -> tuple[str, ...]:
    """The folded first and last tokens of a name (one for a single name)."""
    words = fold(full_name).split()
    if not words:
        return ()
    if len(words) == 1:
        return (words[0],)
    return (words[0], words[-1])


def _contains_word(match_text: str, word: str) -> bool:
    return f" {word} " in f" {match_text} "


def match_folder(match_text: str, consultants: list[ConsultantName]) -> FolderMatch:
    """Match a folder's folded name (``FolderName.match_text``) to consultants."""
    candidates: list[ConsultantName] = []
    full: list[ConsultantName] = []
    for consultant in consultants:
        tokens = name_tokens(consultant.full_name)
        hits = [t for t in tokens if _contains_word(match_text, t)]
        if not hits:
            continue
        candidates.append(consultant)
        if len(hits) == len(tokens):
            full.append(consultant)

    if not candidates:
        return FolderMatch(FolderMatchStatus.UNMATCHED)
    if len(candidates) == 1:
        return FolderMatch(FolderMatchStatus.MATCHED, consultant_id=candidates[0].id)
    if len(full) == 1:
        return FolderMatch(FolderMatchStatus.MATCHED, consultant_id=full[0].id)
    # Two people who share a full name are the real choice; otherwise every
    # consultant the name may mean.
    choices = full if full else candidates
    return FolderMatch(
        FolderMatchStatus.NEEDS_CHOICE, candidate_ids=[c.id for c in choices]
    )
