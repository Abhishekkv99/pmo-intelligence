import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import JobStatus, check_in


class ProcessingJob(Base, UUIDMixin, TimestampMixin):
    """A durable record of one pipeline run.

    ``kind`` names the pipeline (session, chat, health recompute) and
    ``subject_id`` the row it ran for. ``subject_id`` carries no foreign key
    because the subject's table depends on ``kind``.
    """

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            check_in("status", JobStatus), name="ck_processing_jobs_status"
        ),
        Index("ix_processing_jobs_kind_subject", "kind", "subject_id"),
    )

    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.PENDING.value,
        server_default=JobStatus.PENDING.value,
    )
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    def __repr__(self) -> str:
        return f"<ProcessingJob id={self.id} kind={self.kind!r} status={self.status!r}>"
