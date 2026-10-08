"""create recording scans

One row per pass over the PMO recordings folder: when it ran, what it found
and how it ended, so the Admin page can show the last scan and a scan that
keeps failing.

Revision ID: 004
Revises: 003
Create Date: 2026-10-08 22:24:20.251784

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recording_scans",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="running", nullable=False
        ),
        sa.Column("folders_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("folders_added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("folders_matched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recordings_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recordings_added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            "status IN ('running', 'completed', 'failed')",
            name="ck_recording_scans_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recording_scans_started_at"),
        "recording_scans",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_recording_scans_started_at"), table_name="recording_scans")
    op.drop_table("recording_scans")
