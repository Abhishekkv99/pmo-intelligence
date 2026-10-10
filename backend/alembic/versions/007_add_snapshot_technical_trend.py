"""add the technical trend to health snapshots

``technical_trend`` and ``technical_trend_delta``: the change in the
Technical score over the trend window, as ``trend`` is for the overall. An
SME sees only the Technical dimension, so the board shows them this arrow
rather than the overall's, which would reveal how the overall moved.

Revision ID: 007
Revises: 006
Create Date: 2026-10-10 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | Sequence[str] | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "health_snapshots",
        sa.Column("technical_trend", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "health_snapshots",
        sa.Column("technical_trend_delta", sa.Float(), nullable=True),
    )
    op.create_check_constraint(
        "ck_health_snapshots_technical_trend",
        "health_snapshots",
        "technical_trend IN ('up', 'flat', 'down')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_health_snapshots_technical_trend", "health_snapshots", type_="check"
    )
    op.drop_column("health_snapshots", "technical_trend_delta")
    op.drop_column("health_snapshots", "technical_trend")
