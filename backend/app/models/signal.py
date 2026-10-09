"""What the pipelines read from sessions and messages: signals, issues, actions.

``signals`` is the one table the health model reads. Every signal carries the
quote it was read from, found in its source before it was stored. An issue
is a blocker followed across calls; an action is what was agreed.

``source_id`` is a session or a message id, by ``source_kind``, so it has no
foreign key.
"""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    SEVERITY_MAX,
    SEVERITY_MIN,
    ActionStatus,
    Dimension,
    IssueStatus,
    Polarity,
    SignalCategory,
    SignalIndicator,
    SourceKind,
    SpeakerRole,
    check_in,
)

EMBEDDING_DIMENSIONS = 1536


class Issue(Base, UUIDMixin, TimestampMixin):
    """A blocker followed across calls; the repeated-blocker trigger reads it."""

    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint(check_in("status", IssueStatus), name="ck_issues_status"),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IssueStatus.OPEN.value,
        server_default=IssueStatus.OPEN.value,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Signal(Base, UUIDMixin, TimestampMixin):
    """One piece of evidence about a placement, with the words it came from."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            check_in("source_kind", SourceKind), name="ck_signals_source_kind"
        ),
        CheckConstraint(
            check_in("category", SignalCategory), name="ck_signals_category"
        ),
        CheckConstraint(check_in("dimension", Dimension), name="ck_signals_dimension"),
        CheckConstraint(check_in("polarity", Polarity), name="ck_signals_polarity"),
        CheckConstraint(
            f"severity BETWEEN {SEVERITY_MIN} AND {SEVERITY_MAX}",
            name="ck_signals_severity",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"
        ),
        CheckConstraint(
            check_in("speaker_role", SpeakerRole), name="ck_signals_speaker_role"
        ),
        CheckConstraint(
            check_in("indicator", SignalIndicator), name="ck_signals_indicator"
        ),
        Index("ix_signals_placement_id_occurred_at", "placement_id", "occurred_at"),
        Index("ix_signals_source_kind_source_id", "source_kind", "source_id"),
        # For "who else had this blocker": OpenAI embeddings are unit length,
        # so cosine distance is the measure.
        Index(
            "ix_signals_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who said the quote: the role of the utterance it was found in.
    speaker_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Where the quote starts in the recording; NULL for a message.
    offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # What the signal says outright that a critical trigger reads (client
    # dissatisfaction, a change of consultant asked for, intent to leave).
    indicator: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The quote and note, embedded after the session's analysis is stored.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )


class Action(Base, UUIDMixin, TimestampMixin):
    """Something agreed on a call or in the group, with who owns it."""

    __tablename__ = "actions"
    __table_args__ = (
        CheckConstraint(
            check_in("source_kind", SourceKind), name="ck_actions_source_kind"
        ),
        CheckConstraint(
            check_in("owner_role", SpeakerRole), name="ck_actions_owner_role"
        ),
        CheckConstraint(check_in("status", ActionStatus), name="ck_actions_status"),
        Index("ix_actions_source_kind_source_id", "source_kind", "source_id"),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Set when the owner is the placement's PS, SME or tech lead.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # The words where it was agreed, found in the source before it was stored.
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    offset_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ActionStatus.OPEN.value,
        server_default=ActionStatus.OPEN.value,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The session or message that closed it.
    closed_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
