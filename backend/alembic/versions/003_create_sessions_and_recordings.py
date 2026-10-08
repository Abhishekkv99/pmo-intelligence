"""create sessions and recordings

The recordings folder catalog (``recording_folders``, ``source_recordings``),
recorded PMO sessions and their transcripts, and the foreign key from
``processing_costs.session_id`` that migration 001 left out until
``sessions`` existed. A session links to its recording in one direction
(``sessions.source_recording_id``, unique).

Revision ID: 003
Revises: 002
Create Date: 2026-10-08 21:52:02.100394

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recording_folders",
        sa.Column("folder_key", sa.String(length=1024), nullable=False),
        sa.Column("display_name", sa.String(length=1024), nullable=False),
        sa.Column("folder_date", sa.Date(), nullable=True),
        sa.Column("consultant_id", sa.UUID(), nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=20),
            server_default="unmatched",
            nullable=False,
        ),
        sa.Column(
            "candidate_consultant_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
            "match_status IN ('matched', 'chosen', 'needs_choice', 'unmatched')",
            name="ck_recording_folders_match_status",
        ),
        sa.ForeignKeyConstraint(
            ["consultant_id"], ["consultants.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("folder_key"),
    )
    op.create_index(
        op.f("ix_recording_folders_consultant_id"),
        "recording_folders",
        ["consultant_id"],
        unique=False,
    )
    op.create_table(
        "source_recordings",
        sa.Column("folder_id", sa.UUID(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
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
            ["folder_id"], ["recording_folders.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_source_recordings_folder_id"),
        "source_recordings",
        ["folder_id"],
        unique=False,
    )
    op.create_table(
        "sessions",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("kind_overridden_by_user_id", sa.UUID(), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("recording_key", sa.String(length=1024), nullable=True),
        sa.Column("source_recording_id", sa.UUID(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=True),
        sa.Column("graph_meeting_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="uploaded", nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("quotes_rejected", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "node_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
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
        sa.CheckConstraint(
            "kind IN ('onboarding', 'technical', 'check_in', 'escalation', 'other')",
            name="ck_sessions_kind",
        ),
        sa.CheckConstraint(
            "source IN ('s3', 'upload', 'url', 'graph')", name="ck_sessions_source"
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'transcribing', 'transcribed', 'analyzing', "
            "'completed', 'failed')",
            name="ck_sessions_status",
        ),
        sa.ForeignKeyConstraint(
            ["kind_overridden_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_recording_id"], ["source_recordings.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_recording_id"),
    )
    op.create_index(
        op.f("ix_sessions_placement_id"), "sessions", ["placement_id"], unique=False
    )
    op.create_index(op.f("ix_sessions_status"), "sessions", ["status"], unique=False)
    op.create_table(
        "session_transcripts",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("utterances", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "speaker_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("session_class", sa.String(length=20), nullable=True),
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
            "session_class IN "
            "('onboarding', 'technical', 'check_in', 'escalation', 'other')",
            name="ck_session_transcripts_session_class",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_foreign_key(
        "processing_costs_session_id_fkey",
        "processing_costs",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "processing_costs_session_id_fkey", "processing_costs", type_="foreignkey"
    )
    op.drop_table("session_transcripts")
    op.drop_index(op.f("ix_sessions_status"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_placement_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(
        op.f("ix_source_recordings_folder_id"), table_name="source_recordings"
    )
    op.drop_table("source_recordings")
    op.drop_index(
        op.f("ix_recording_folders_consultant_id"), table_name="recording_folders"
    )
    op.drop_table("recording_folders")
