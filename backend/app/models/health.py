"""What the health model writes: a snapshot per recompute, and risk flags.

A ``health_snapshots`` row is one reading of a placement: its six dimension
scores, overall, trend and RAG level, with the signals that moved each
dimension most, so the page shows why exactly as it was computed. The board
reads the latest row; the chart reads the history. A placement with no
signals in the lookback is not scored: every score column is NULL.

A ``risk_flags`` row stays open until a person closes it (Phase 4). At most
one open flag per placement, trigger and subject (an issue, for a repeated
blocker; ``''`` for a trigger without one), so a recompute adds new evidence
to the open flag rather than opening another.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    FlagSeverity,
    RiskLevel,
    RiskTrigger,
    SnapshotReason,
    Trend,
    check_in,
)


class HealthSnapshot(Base, UUIDMixin, TimestampMixin):
    """One health reading of a placement, stored after every recompute."""

    __tablename__ = "health_snapshots"
    __table_args__ = (
        CheckConstraint(
            check_in("reason", SnapshotReason), name="ck_health_snapshots_reason"
        ),
        CheckConstraint(check_in("trend", Trend), name="ck_health_snapshots_trend"),
        CheckConstraint(
            check_in("technical_trend", Trend),
            name="ck_health_snapshots_technical_trend",
        ),
        CheckConstraint(
            check_in("risk_level", RiskLevel), name="ck_health_snapshots_risk_level"
        ),
        Index(
            "ix_health_snapshots_placement_id_computed_at",
            "placement_id",
            "computed_at",
        ),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    # False when the placement had no signals in the lookback; the scores,
    # trend and risk level are then NULL.
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False)
    delivery: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical: Mapped[float | None] = mapped_column(Float, nullable=True)
    relationship: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement: Mapped[float | None] = mapped_column(Float, nullable=True)
    onboarding: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    # NULL until there is a score at the start of the trend window to compare.
    trend: Mapped[str | None] = mapped_column(String(10), nullable=True)
    trend_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The same for the Technical score alone: what an SME sees, since the
    # overall's trend would reveal how the overall moved.
    technical_trend: Mapped[str | None] = mapped_column(String(10), nullable=True)
    technical_trend_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    signal_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # The health configuration that produced it (``app/health/config/``).
    weights_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # Per dimension: the signal count and the top contributors, each
    # {signal_id, weight, value}.
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class RiskFlag(Base, UUIDMixin, TimestampMixin):
    """An early warning on a placement, open until a person closes it."""

    __tablename__ = "risk_flags"
    __table_args__ = (
        CheckConstraint(check_in("trigger", RiskTrigger), name="ck_risk_flags_trigger"),
        CheckConstraint(
            check_in("severity", FlagSeverity), name="ck_risk_flags_severity"
        ),
        # NULLs never clash in a unique index, so a trigger without a subject
        # uses '' rather than NULL.
        Index(
            "uq_risk_flags_open",
            "placement_id",
            "trigger",
            "subject_key",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
    )

    placement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("placements.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    # What the flag is about within its trigger: the issue id for a repeated
    # blocker, '' for the others.
    subject_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The signals behind it; a later recompute adds new ones.
    evidence_signal_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
