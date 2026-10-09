"""create signals issues actions

What the session pipeline reads from a call: ``signals`` (the one table the
health model reads; every signal's quote was found in its source), ``issues``
(blockers followed across calls) and ``actions`` (what was agreed, with the
quote that places it in the recording). Also ``session_transcripts.project
_phase`` from the classify node. The ``embedding`` column is filled in
Sprint 2.

Revision ID: 005
Revises: 004
Create Date: 2026-10-09 14:15:45.499595

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "actions",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("owner_role", sa.String(length=20), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("offset_ms", sa.Integer(), nullable=True),
        sa.Column("due_text", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="open", nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_source_id", sa.UUID(), nullable=True),
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
            "owner_role IN ('consultant', 'pmo_manager', 'sme', 'tech_lead', "
            "'ps', 'other')",
            name="ck_actions_owner_role",
        ),
        sa.CheckConstraint(
            "source_kind IN ('session', 'message')", name="ck_actions_source_kind"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'overdue')", name="ck_actions_status"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_actions_owner_user_id"), "actions", ["owner_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_actions_placement_id"), "actions", ["placement_id"], unique=False
    )
    op.create_index(
        "ix_actions_source_kind_source_id",
        "actions",
        ["source_kind", "source_id"],
        unique=False,
    )
    op.create_table(
        "issues",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="open", nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_issues_status"),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issues_placement_id"), "issues", ["placement_id"], unique=False
    )
    op.create_table(
        "signals",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("dimension", sa.String(length=20), nullable=False),
        sa.Column("polarity", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("speaker_role", sa.String(length=20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offset_ms", sa.Integer(), nullable=True),
        sa.Column("issue_id", sa.UUID(), nullable=True),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
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
            "category IN ('issue', 'relationship_engagement', 'client')",
            name="ck_signals_category",
        ),
        sa.CheckConstraint(
            "dimension IN ('delivery', 'technical', 'relationship', 'engagement', "
            "'onboarding', 'communication')",
            name="ck_signals_dimension",
        ),
        sa.CheckConstraint(
            "polarity IN ('positive', 'negative', 'neutral')",
            name="ck_signals_polarity",
        ),
        sa.CheckConstraint(
            "source_kind IN ('session', 'message')", name="ck_signals_source_kind"
        ),
        sa.CheckConstraint(
            "speaker_role IN ('consultant', 'pmo_manager', 'sme', 'tech_lead', "
            "'ps', 'other')",
            name="ck_signals_speaker_role",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"
        ),
        sa.CheckConstraint("severity BETWEEN 1 AND 3", name="ck_signals_severity"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_issue_id"), "signals", ["issue_id"], unique=False)
    op.create_index(
        "ix_signals_placement_id_occurred_at",
        "signals",
        ["placement_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_source_kind_source_id",
        "signals",
        ["source_kind", "source_id"],
        unique=False,
    )
    op.add_column(
        "session_transcripts",
        sa.Column("project_phase", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("session_transcripts", "project_phase")
    op.drop_index("ix_signals_source_kind_source_id", table_name="signals")
    op.drop_index("ix_signals_placement_id_occurred_at", table_name="signals")
    op.drop_index(op.f("ix_signals_issue_id"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_issues_placement_id"), table_name="issues")
    op.drop_table("issues")
    op.drop_index("ix_actions_source_kind_source_id", table_name="actions")
    op.drop_index(op.f("ix_actions_placement_id"), table_name="actions")
    op.drop_index(op.f("ix_actions_owner_user_id"), table_name="actions")
    op.drop_table("actions")
