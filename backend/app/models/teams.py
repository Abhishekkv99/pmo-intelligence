"""Teams group chats, their messages, and the Graph subscriptions that watch them.

A PMO group chat is titled ``PRJ ITC <stack> - <consultant> - <client> -
<start> - <end>`` and belongs to one placement. A chat linked to an active
placement is watched: one change-notification subscription per chat, read
with ``Chat.Read.All``. Every message of a watched chat is stored, so a flag
can quote it; a chat that stops being watched keeps what was stored.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    FolderMatchStatus,
    HistoryState,
    MessageClass,
    SpeakerRole,
    TeamsChatMatch,
    TeamsWatchState,
    check_in,
)


class TeamsGroup(Base, UUIDMixin, TimestampMixin):
    """One Teams group chat titled ``PRJ ITC …``, found by discovery."""

    __tablename__ = "teams_groups"
    __table_args__ = (
        CheckConstraint(
            check_in("match_status", TeamsChatMatch),
            name="ck_teams_groups_match_status",
        ),
        CheckConstraint(
            check_in("consultant_member_match", FolderMatchStatus),
            name="ck_teams_groups_consultant_member_match",
        ),
        CheckConstraint(
            check_in("watch_state", TeamsWatchState),
            name="ck_teams_groups_watch_state",
        ),
        CheckConstraint(
            check_in("history_state", HistoryState),
            name="ck_teams_groups_history_state",
        ),
    )

    graph_chat_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    # The title's parts, as the parser read them; NULL when it could not.
    parsed_stack: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parsed_consultant_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    parsed_client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parsed_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parsed_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    placement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    match_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TeamsChatMatch.UNPARSED.value,
        server_default=TeamsChatMatch.UNPARSED.value,
    )
    # Placement ids the title could belong to, when several could.
    candidate_placement_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # The chat's members as last read: [{"oid": ..., "name": ...}].
    members: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # Which member is the placement's consultant (their Entra object id).
    consultant_member_oid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consultant_member_match: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FolderMatchStatus.UNMATCHED.value,
        server_default=FolderMatchStatus.UNMATCHED.value,
    )
    watch_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TeamsWatchState.NOT_WATCHED.value,
        server_default=TeamsWatchState.NOT_WATCHED.value,
    )
    watched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # A notification (or the catch-up) asked for a sync at this time; a
    # takeover queues the chat again while it is newer than last_synced_at.
    sync_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The watermark: messages changed after it are read by the next sync.
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    history_state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=HistoryState.NONE.value,
        server_default=HistoryState.NONE.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Message(Base, UUIDMixin, TimestampMixin):
    """One message of a watched chat, kept so a flag can quote it."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "teams_group_id",
            "graph_message_id",
            name="uq_messages_teams_group_id_graph_message_id",
        ),
        CheckConstraint(
            check_in("author_role", SpeakerRole), name="ck_messages_author_role"
        ),
        CheckConstraint(
            check_in("message_class", MessageClass), name="ck_messages_message_class"
        ),
        Index("ix_messages_teams_group_id_posted_at", "teams_group_id", "posted_at"),
    )

    teams_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams_groups.id", ondelete="RESTRICT"),
        nullable=False,
    )
    graph_message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # NULL for a system event, which has no user author.
    author_entra_oid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Deleted in Teams: the time is kept and the text cleared.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    body_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # The Graph id of the message this one replies to.
    reply_to_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Graph's messageType as given (``message``, ``systemEventMessage``, …);
    # no CHECK, since Microsoft adds values. Only ``message`` is analysed.
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # NULL until the chat pipeline classifies it.
    message_class: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_noise: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Read with the chat's history when it was first watched; analysed only
    # once a person asks.
    is_history: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    analysed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GraphSubscription(Base, UUIDMixin, TimestampMixin):
    """The change-notification subscription to one watched chat's messages."""

    __tablename__ = "graph_subscriptions"

    subscription_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    teams_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams_groups.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    # The subscribed resource, ``/chats/{id}/messages``.
    resource: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
