"""Request and response models for the recordings folder (Admin > Recordings)."""

import uuid
from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl

from app.models.enums import (
    FolderMatchStatus,
    PlacementStatus,
    ScanStatus,
    SessionSource,
    SessionStatus,
)


class ConsultantRef(BaseModel):
    id: uuid.UUID
    full_name: str


class RecordingSessionRef(BaseModel):
    id: uuid.UUID
    status: SessionStatus


class RecordingItem(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    # From the file name; the S3 time when ``time_from_name`` is false.
    recorded_at: datetime
    time_from_name: bool
    session: RecordingSessionRef | None


class RecordingFolderItem(BaseModel):
    id: uuid.UUID
    display_name: str
    folder_date: date | None
    match_status: FolderMatchStatus
    consultant: ConsultantRef | None
    candidates: list[ConsultantRef]
    last_seen_at: datetime
    recordings: list[RecordingItem]


class ScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: ScanStatus
    folders_seen: int
    folders_added: int
    folders_matched: int
    recordings_seen: int
    recordings_added: int
    error_message: str | None


class RecordingFolderList(BaseModel):
    folders: list[RecordingFolderItem]
    latest_scan: ScanSummary | None
    scan_enabled: bool
    scan_interval_seconds: int


class ChooseConsultant(BaseModel):
    consultant_id: uuid.UUID


class ScanRequested(BaseModel):
    queued: bool


class ProcessRecording(BaseModel):
    placement_id: uuid.UUID | None = None


class PlacementOption(BaseModel):
    id: uuid.UUID
    client_name: str
    project_name: str
    start_date: date
    expected_end_date: date | None
    status: PlacementStatus


class PlacementChoice(BaseModel):
    """The 409 body when Process needs a placement chosen."""

    detail: str
    placements: list[PlacementOption]


class SessionCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    placement_id: uuid.UUID
    source: SessionSource
    status: SessionStatus
    held_at: datetime


class UrlSessionCreate(BaseModel):
    url: HttpUrl
    placement_id: uuid.UUID
    held_at: AwareDatetime
