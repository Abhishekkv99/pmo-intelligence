"""Tie a PMO group chat to its placement from the chat's title.

A placement is a candidate when its client has the title's client name
(normalised: case and spacing ignored), it starts on the title's start date,
and its consultant's first or last name is a whole word of the title's
consultant name, as recording folders are matched (``name_match``). Any
project of the client counts, so renaming a placement's project keeps it, and
any status, so an old chat finds its ended placement.

Exactly one candidate is a match. Several are resolved only when one
consultant has both names in the title and has one placement among them;
otherwise a person chooses on Admin > Teams. No candidate is unmatched, and
the page offers to create the placement from the title.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.models.enums import FolderMatchStatus, TeamsChatMatch
from app.services.recordings.folder_names import fold
from app.services.recordings.name_match import ConsultantName, match_folder
from app.services.register_service import normalize_name
from app.services.teams.chat_titles import ChatTitle


@dataclass(frozen=True)
class PlacementCandidate:
    placement_id: uuid.UUID
    consultant_id: uuid.UUID
    consultant_name: str
    client_name: str
    start_date: date


@dataclass(frozen=True)
class ChatMatch:
    status: TeamsChatMatch
    placement_id: uuid.UUID | None = None
    candidate_ids: list[uuid.UUID] = field(default_factory=list)


def match_chat(title: ChatTitle, placements: list[PlacementCandidate]) -> ChatMatch:
    client = normalize_name(title.client)
    same_start = [
        p
        for p in placements
        if p.start_date == title.start_date and normalize_name(p.client_name) == client
    ]
    consultants = {
        p.consultant_id: ConsultantName(p.consultant_id, p.consultant_name)
        for p in same_start
    }
    found = match_folder(fold(title.consultant), list(consultants.values()))
    if found.status == FolderMatchStatus.UNMATCHED:
        return ChatMatch(TeamsChatMatch.UNMATCHED)

    chosen = (
        {found.consultant_id}
        if found.status == FolderMatchStatus.MATCHED
        else set(found.candidate_ids)
    )
    candidates = [p.placement_id for p in same_start if p.consultant_id in chosen]
    if len(candidates) == 1:
        return ChatMatch(TeamsChatMatch.MATCHED, placement_id=candidates[0])
    return ChatMatch(TeamsChatMatch.NEEDS_CHOICE, candidate_ids=candidates)
