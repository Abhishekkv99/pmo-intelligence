"""add the stack to placements

``placements.stack``: the consultant's stack on this engagement (``DS``,
``BD``), as the Teams chat and recordings folder names give it
(``PRJ ITC DS - <consultant> - <client> - <start> - <end>``). Free text, set by
the quick add or the placement dialog; empty for older placements.

Revision ID: 008
Revises: 007
Create Date: 2026-10-11 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | Sequence[str] | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("placements", sa.Column("stack", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("placements", "stack")
