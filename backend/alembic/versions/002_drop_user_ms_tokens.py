"""drop the stored Microsoft tokens from users

Sign-in no longer keeps the user's Microsoft access or refresh token: PMO
reads Teams with the Graph app's own credential, so the tokens served no
purpose and were sensitive data at rest. Downgrade restores the empty
columns; the dropped values are not recoverable.

Revision ID: 002
Revises: 001
Create Date: 2026-10-08 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("users", "ms_token_expires_at")
    op.drop_column("users", "ms_refresh_token")
    op.drop_column("users", "ms_access_token")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("users", sa.Column("ms_access_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("ms_refresh_token", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("ms_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
