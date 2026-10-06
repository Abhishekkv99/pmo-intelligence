"""The placement register: consultants, clients, projects and placements.

The placement is the unit of health; the consultant, the client and the
project are its context (docs/PRD.md, "Data model draft").
"""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    ConsultantStatus,
    ExtensionStatus,
    PlacementStatus,
    check_in,
)


class Consultant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "consultants"
    __table_args__ = (
        CheckConstraint(
            check_in("status", ConsultantStatus), name="ck_consultants_status"
        ),
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    # Links a Teams message author to the consultant.
    entra_oid: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skills: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ConsultantStatus.PLACED.value,
        server_default=ConsultantStatus.PLACED.value,
    )


class Client(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Lower-cased, whitespace-collapsed name; the dedup key.
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tech_lead_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Placement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "placements"
    __table_args__ = (
        CheckConstraint(
            check_in("extension_status", ExtensionStatus),
            name="ck_placements_extension_status",
        ),
        CheckConstraint(
            check_in("status", PlacementStatus), name="ck_placements_status"
        ),
    )

    consultant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    extension_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ExtensionStatus.NOT_DUE.value,
        server_default=ExtensionStatus.NOT_DUE.value,
    )
    rate_band: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ps_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sme_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PlacementStatus.ACTIVE.value,
        server_default=PlacementStatus.ACTIVE.value,
    )
    # Why a placement ended; what a forecast model would later learn from.
    ended_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
