"""Admin > Teams: the PMO group chats, their placement and who is watched."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    FolderMatchStatus,
    HistoryState,
    PlacementStatus,
    ScanStatus,
    TeamsChatMatch,
    TeamsWatchState,
)


class TeamsScanSummary(BaseModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: ScanStatus
    chats_seen: int
    chats_added: int
    chats_matched: int
    error_message: str | None


class TeamsPlacement(BaseModel):
    """A placement a chat is, or may be, tied to."""

    id: uuid.UUID
    consultant_name: str
    client_name: str
    project_name: str
    start_date: date
    expected_end_date: date | None
    status: PlacementStatus


class TeamsMember(BaseModel):
    oid: str
    name: str


class ParsedTitle(BaseModel):
    stack: str
    consultant: str
    client: str
    start_date: date
    end_date: date


class TeamsChatItem(BaseModel):
    id: uuid.UUID
    title: str
    # The title's parts as read; null when the title could not be read.
    parsed: ParsedTitle | None
    # The title as a quick add line, for "Create placement from title".
    quick_add_line: str
    match_status: TeamsChatMatch
    placement: TeamsPlacement | None
    candidates: list[TeamsPlacement]
    watch_state: TeamsWatchState
    watched_at: datetime | None
    stopped_at: datetime | None
    members: list[TeamsMember]
    consultant_member: TeamsMember | None
    consultant_member_match: FolderMatchStatus
    last_message_at: datetime | None
    history_state: HistoryState
    # Why the title was not read, or why the members were not.
    error_message: str | None


class TeamsChatList(BaseModel):
    chats: list[TeamsChatItem]
    latest_scan: TeamsScanSummary | None
    discovery_enabled: bool
    watching_enabled: bool


class ChooseChatPlacement(BaseModel):
    placement_id: uuid.UUID


class CreatePlacementFromTitle(BaseModel):
    """One quick add line, prefilled from the chat's title and maybe edited."""

    line: str = Field(min_length=1, max_length=500)


class ChooseConsultantMember(BaseModel):
    oid: str = Field(min_length=1, max_length=64)
