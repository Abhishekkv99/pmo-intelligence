"""create teams scans

One row per discovery pass over the PMO accounts' chat lists: when it ran,
how many PRJ ITC chats it saw, added and matched, and how it ended, so
Admin > Teams can show the last scan and one that keeps failing.

Revision ID: 011
Revises: 010
Create Date: 2026-10-18 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | Sequence[str] | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "teams_scans",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="running", nullable=False
        ),
        sa.Column("chats_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chats_added", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chats_matched", sa.Integer(), server_default="0", nullable=False),
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
            name="ck_teams_scans_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_teams_scans_started_at"), "teams_scans", ["started_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_teams_scans_started_at"), table_name="teams_scans")
    op.drop_table("teams_scans")
