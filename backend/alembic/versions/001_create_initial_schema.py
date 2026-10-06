"""create initial schema

Users and refresh tokens (role-based entitlement), the placement register
(consultants, clients, projects, placements), the processing job and cost
tables, and the access log. Enables pgvector for the signal embeddings that
later migrations add.

Revision ID: 001
Revises:
Create Date: 2026-10-06 16:52:18.191101

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Needs rds_superuser on RDS. In deployed environments the database
    # bootstrap task creates it first, so this is a no-op there.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "clients",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "consultants",
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("entra_oid", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column(
            "skills",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default="placed", nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('bench', 'placed', 'left')", name="ck_consultants_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entra_oid"),
    )
    op.create_index(
        op.f("ix_consultants_email"), "consultants", ["email"], unique=False
    )
    op.create_table(
        "processing_jobs",
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'failed')",
            name="ck_processing_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_jobs_kind_subject",
        "processing_jobs",
        ["kind", "subject_id"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "auth_provider",
            sa.String(length=50),
            server_default="local",
            nullable=False,
        ),
        sa.Column("entra_oid", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("ms_access_token", sa.Text(), nullable=True),
        sa.Column("ms_refresh_token", sa.Text(), nullable=True),
        sa.Column("ms_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IS NULL OR "
            "role IN ('pmo_manager', 'sme', 'tech_lead', 'ps', 'admin')",
            name="ck_users_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_entra_oid"), "users", ["entra_oid"], unique=True)
    op.create_table(
        "processing_costs",
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("processing_job_id", sa.UUID(), nullable=True),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"], ["processing_jobs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_processing_costs_message_id"),
        "processing_costs",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_processing_costs_processing_job_id"),
        "processing_costs",
        ["processing_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_processing_costs_session_id"),
        "processing_costs",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "projects",
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_manager_name", sa.String(length=255), nullable=True),
        sa.Column("tech_lead_user_id", sa.UUID(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tech_lead_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_projects_client_id"), "projects", ["client_id"], unique=False
    )
    op.create_index(
        op.f("ix_projects_tech_lead_user_id"),
        "projects",
        ["tech_lead_user_id"],
        unique=False,
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "placements",
        sa.Column("consultant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("expected_end_date", sa.Date(), nullable=True),
        sa.Column(
            "extension_status",
            sa.String(length=20),
            server_default="not_due",
            nullable=False,
        ),
        sa.Column("rate_band", sa.String(length=50), nullable=True),
        sa.Column("ps_user_id", sa.UUID(), nullable=True),
        sa.Column("sme_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="active", nullable=False
        ),
        sa.Column("ended_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "extension_status IN "
            "('not_due', 'due', 'requested', 'confirmed', 'declined')",
            name="ck_placements_extension_status",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'ended', 'terminated')", name="ck_placements_status"
        ),
        sa.ForeignKeyConstraint(
            ["consultant_id"], ["consultants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ps_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sme_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_placements_consultant_id"),
        "placements",
        ["consultant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_placements_project_id"), "placements", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_placements_ps_user_id"), "placements", ["ps_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_placements_sme_user_id"), "placements", ["sme_user_id"], unique=False
    )
    op.create_table(
        "access_log",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("route", sa.String(length=500), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_log_placement_at", "access_log", ["placement_id", "at"], unique=False
    )
    op.create_index(
        op.f("ix_access_log_user_id"), "access_log", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema. The vector extension is left in place."""
    op.drop_index(op.f("ix_access_log_user_id"), table_name="access_log")
    op.drop_index("ix_access_log_placement_at", table_name="access_log")
    op.drop_table("access_log")
    op.drop_index(op.f("ix_placements_sme_user_id"), table_name="placements")
    op.drop_index(op.f("ix_placements_ps_user_id"), table_name="placements")
    op.drop_index(op.f("ix_placements_project_id"), table_name="placements")
    op.drop_index(op.f("ix_placements_consultant_id"), table_name="placements")
    op.drop_table("placements")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_projects_tech_lead_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_client_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_processing_costs_session_id"), table_name="processing_costs")
    op.drop_index(
        op.f("ix_processing_costs_processing_job_id"), table_name="processing_costs"
    )
    op.drop_index(op.f("ix_processing_costs_message_id"), table_name="processing_costs")
    op.drop_table("processing_costs")
    op.drop_index(op.f("ix_users_entra_oid"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index("ix_processing_jobs_kind_subject", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index(op.f("ix_consultants_email"), table_name="consultants")
    op.drop_table("consultants")
    op.drop_table("clients")
