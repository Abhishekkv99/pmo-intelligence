"""create health snapshots and risk flags

What the health model writes: ``health_snapshots`` (one reading per
recompute, with the signals that moved each dimension most) and
``risk_flags`` (open until a person closes it; one open flag per placement,
trigger and subject). Also ``signals.indicator``, which the critical
triggers read, and an HNSW index for cosine search over signal embeddings.

Revision ID: 006
Revises: 005
Create Date: 2026-10-09 23:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "health_snapshots",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("scored", sa.Boolean(), nullable=False),
        sa.Column("delivery", sa.Float(), nullable=True),
        sa.Column("technical", sa.Float(), nullable=True),
        sa.Column("relationship", sa.Float(), nullable=True),
        sa.Column("engagement", sa.Float(), nullable=True),
        sa.Column("onboarding", sa.Float(), nullable=True),
        sa.Column("communication", sa.Float(), nullable=True),
        sa.Column("overall", sa.Float(), nullable=True),
        sa.Column("trend", sa.String(length=10), nullable=True),
        sa.Column("trend_delta", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=10), nullable=True),
        sa.Column("signal_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("weights_version", sa.String(length=20), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "reason IN ('call', 'register', 'daily', 'catch_up')",
            name="ck_health_snapshots_reason",
        ),
        sa.CheckConstraint(
            "trend IN ('up', 'flat', 'down')", name="ck_health_snapshots_trend"
        ),
        sa.CheckConstraint(
            "risk_level IN ('green', 'amber', 'red')",
            name="ck_health_snapshots_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_snapshots_placement_id_computed_at",
        "health_snapshots",
        ["placement_id", "computed_at"],
        unique=False,
    )
    op.create_table(
        "risk_flags",
        sa.Column("placement_id", sa.UUID(), nullable=False),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column(
            "subject_key", sa.String(length=100), server_default="", nullable=False
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "evidence_signal_ids",
            postgresql.ARRAY(sa.UUID()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("closing_note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "trigger IN ('gone_quiet', 'client_dissatisfaction', "
            "'repeated_blocker', 'downward_trend', 'relationship_strain', "
            "'contract_horizon', 'intent_to_leave', 'missed_commitment')",
            name="ck_risk_flags_trigger",
        ),
        sa.CheckConstraint(
            "severity IN ('medium', 'high', 'critical')",
            name="ck_risk_flags_severity",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_flags_placement_id"),
        "risk_flags",
        ["placement_id"],
        unique=False,
    )
    op.create_index(
        "uq_risk_flags_open",
        "risk_flags",
        ["placement_id", "trigger", "subject_key"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.add_column(
        "signals", sa.Column("indicator", sa.String(length=40), nullable=True)
    )
    op.create_check_constraint(
        "ck_signals_indicator",
        "signals",
        "indicator IN ('client_dissatisfaction', 'consultant_change_requested', "
        "'intent_to_leave')",
    )
    op.create_index(
        "ix_signals_embedding_hnsw",
        "signals",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_signals_embedding_hnsw",
        table_name="signals",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_constraint("ck_signals_indicator", "signals", type_="check")
    op.drop_column("signals", "indicator")
    op.drop_index(
        "uq_risk_flags_open",
        table_name="risk_flags",
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.drop_index(op.f("ix_risk_flags_placement_id"), table_name="risk_flags")
    op.drop_table("risk_flags")
    op.drop_index(
        "ix_health_snapshots_placement_id_computed_at",
        table_name="health_snapshots",
    )
    op.drop_table("health_snapshots")
