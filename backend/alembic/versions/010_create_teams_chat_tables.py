"""create the teams chat tables

Teams chat (Sprint 4): the PMO group chats, their messages, and the Graph
change-notification subscription that watches each one.

- ``teams_groups``: one row per chat titled ``PRJ ITC …``, with the title's
  parsed parts, the placement it belongs to (matched or chosen), its members
  and which of them is the consultant, whether it is watched, the sync
  watermark and the history state. The draft's ``kind``, ``graph_team_id``,
  ``graph_channel_id`` and ``delta_token`` are not built: PMO groups are
  group chats, and an app has no delta query for chats.
- ``messages``: every message of a watched chat, unique by (chat, Graph id).
- ``graph_subscriptions``: one per watched chat (``/chats/{id}/messages``).
- ``processing_costs.message_id`` gains its foreign key (``ON DELETE SET
  NULL``, as ``session_id``).
- ``health_snapshots.reason`` allows ``chat``.

Revision ID: 010
Revises: 009
Create Date: 2026-10-18 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | Sequence[str] | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS_NEW = "reason IN ('call', 'chat', 'register', 'daily', 'catch_up')"
REASONS_OLD = "reason IN ('call', 'register', 'daily', 'catch_up')"


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
        "teams_groups",
        sa.Column("graph_chat_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("parsed_stack", sa.String(length=50), nullable=True),
        sa.Column("parsed_consultant_name", sa.String(length=255), nullable=True),
        sa.Column("parsed_client_name", sa.String(length=255), nullable=True),
        sa.Column("parsed_start_date", sa.Date(), nullable=True),
        sa.Column("parsed_end_date", sa.Date(), nullable=True),
        sa.Column("placement_id", sa.UUID(), nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=20),
            server_default="unparsed",
            nullable=False,
        ),
        sa.Column(
            "candidate_placement_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "members",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("consultant_member_oid", sa.String(length=64), nullable=True),
        sa.Column(
            "consultant_member_match",
            sa.String(length=20),
            server_default="unmatched",
            nullable=False,
        ),
        sa.Column(
            "watch_state",
            sa.String(length=20),
            server_default="not_watched",
            nullable=False,
        ),
        sa.Column("watched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "history_state", sa.String(length=20), server_default="none", nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "match_status IN "
            "('matched', 'chosen', 'needs_choice', 'unmatched', 'unparsed')",
            name="ck_teams_groups_match_status",
        ),
        sa.CheckConstraint(
            "consultant_member_match IN "
            "('matched', 'chosen', 'needs_choice', 'unmatched')",
            name="ck_teams_groups_consultant_member_match",
        ),
        sa.CheckConstraint(
            "watch_state IN ('not_watched', 'watching', 'stopped', 'failed')",
            name="ck_teams_groups_watch_state",
        ),
        sa.CheckConstraint(
            "history_state IN ('none', 'stored', 'analysing', 'analysed')",
            name="ck_teams_groups_history_state",
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"], ["placements.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_chat_id"),
    )
    op.create_index(
        op.f("ix_teams_groups_placement_id"),
        "teams_groups",
        ["placement_id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("teams_group_id", sa.UUID(), nullable=False),
        sa.Column("graph_message_id", sa.String(length=100), nullable=False),
        sa.Column("author_entra_oid", sa.String(length=64), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("author_role", sa.String(length=20), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column("reply_to_message_id", sa.String(length=100), nullable=True),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("message_class", sa.String(length=30), nullable=True),
        sa.Column("is_noise", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_history", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "author_role IN ('consultant', 'pmo_manager', 'sme', 'cdm', 'ps', 'other')",
            name="ck_messages_author_role",
        ),
        sa.CheckConstraint(
            "message_class IN ('consultant_update', 'question', "
            "'stakeholder_context', 'praise', 'concern', 'escalation', "
            "'administrative', 'noise')",
            name="ck_messages_message_class",
        ),
        sa.ForeignKeyConstraint(
            ["teams_group_id"], ["teams_groups.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "teams_group_id",
            "graph_message_id",
            name="uq_messages_teams_group_id_graph_message_id",
        ),
    )
    op.create_index(
        "ix_messages_teams_group_id_posted_at",
        "messages",
        ["teams_group_id", "posted_at"],
        unique=False,
    )

    op.create_table(
        "graph_subscriptions",
        sa.Column("subscription_id", sa.String(length=100), nullable=False),
        sa.Column("teams_group_id", sa.UUID(), nullable=False),
        sa.Column("resource", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["teams_group_id"], ["teams_groups.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id"),
        sa.UniqueConstraint("teams_group_id"),
    )
    op.create_index(
        op.f("ix_graph_subscriptions_expires_at"),
        "graph_subscriptions",
        ["expires_at"],
        unique=False,
    )

    op.create_foreign_key(
        "processing_costs_message_id_fkey",
        "processing_costs",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("ck_health_snapshots_reason", "health_snapshots", type_="check")
    op.create_check_constraint(
        "ck_health_snapshots_reason", "health_snapshots", REASONS_NEW
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Snapshots of chat analysis have no older reason to fall back to.
    op.execute("DELETE FROM health_snapshots WHERE reason = 'chat'")
    op.drop_constraint("ck_health_snapshots_reason", "health_snapshots", type_="check")
    op.create_check_constraint(
        "ck_health_snapshots_reason", "health_snapshots", REASONS_OLD
    )

    op.drop_constraint(
        "processing_costs_message_id_fkey", "processing_costs", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_graph_subscriptions_expires_at"), table_name="graph_subscriptions"
    )
    op.drop_table("graph_subscriptions")
    op.drop_index("ix_messages_teams_group_id_posted_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_teams_groups_placement_id"), table_name="teams_groups")
    op.drop_table("teams_groups")
