"""Recorded PMO sessions, their transcripts, and the recordings folder catalog.

A folder in the PMO recordings bucket is a recurring Talk room tied to one
consultant; each recording file in it is one call, and becomes a session only
when a person presses Process. Uploads and URLs create sessions directly.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    FolderMatchStatus,
    ScanStatus,
    SessionKind,
    SessionSource,
    SessionStatus,
    check_in,
)


class RecordingFolder(Base, UUIDMixin, TimestampMixin):
    """One folder (a recurring Talk room) under the recordings prefix."""

    __tablename__ = "recording_folders"
    __table_args__ = (
        CheckConstraint(
            check_in("match_status", FolderMatchStatus),
            name="ck_recording_folders_match_status",
        ),
    )

    folder_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    # The folder name as shown: suffix stripped, mis-decoded dashes repaired.
    display_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    folder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consultant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    match_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FolderMatchStatus.UNMATCHED.value,
        server_default=FolderMatchStatus.UNMATCHED.value,
    )
    # Consultant ids whose name the folder name contains, when several do.
    candidate_consultant_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SourceRecording(Base, UUIDMixin, TimestampMixin):
    """One recording file in a folder; one call."""

    __tablename__ = "source_recordings"

    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recording_folders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # From the file name's timestamp; NULL when the name does not carry one,
    # and the page then shows ``last_modified``, marked as such.
    recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RecordingScan(Base, UUIDMixin, TimestampMixin):
    """One pass over the recordings folder: what it found, and how it ended."""

    __tablename__ = "recording_scans"
    __table_args__ = (
        CheckConstraint(
            check_in("status", ScanStatus), name="ck_recording_scans_status"
        ),
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ScanStatus.RUNNING.value,
        server_default=ScanStatus.RUNNING.value,
    )
    folders_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    folders_added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Folders tied to a consultant by this pass (new, or newly resolved).
    folders_matched: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    recordings_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    recordings_added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Session(Base, UUIDMixin, TimestampMixin):
    """One recorded PMO call for one placement."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(check_in("kind", SessionKind), name="ck_sessions_kind"),
        CheckConstraint(check_in("source", SessionSource), name="ck_sessions_source"),
        CheckConstraint(check_in("status", SessionStatus), name="ck_sessions_status"),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # NULL until the pipeline classifies the call or a person sets it.
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kind_overridden_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # The copy in PMO's media bucket; set once the recording is stored there.
    recording_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_recordings.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    graph_meeting_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SessionStatus.UPLOADED.value,
        server_default=SessionStatus.UPLOADED.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Signals dropped because their quote was not found in the transcript.
    quotes_rejected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    node_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )


class SessionTranscript(Base, UUIDMixin, TimestampMixin):
    """The diarized transcript of a session and what the pipeline read from it."""

    __tablename__ = "session_transcripts"
    __table_args__ = (
        CheckConstraint(
            check_in("session_class", SessionKind),
            name="ck_session_transcripts_session_class",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    utterances: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    # Diarized speaker label → role, from the role-attribution node.
    speaker_roles: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The kind the classify node chose; ``sessions.kind`` holds the one in use.
    session_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
