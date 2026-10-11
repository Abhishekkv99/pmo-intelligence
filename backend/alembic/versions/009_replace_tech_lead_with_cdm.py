"""replace the tech lead with the consultant director (CDM)

There is no tech lead on the consultancy side. The Consultant Director (CDM)
manages the consultant for the consultancy (mostly management, partly
technical), and one CDM manages several consultants, so the CDM sits on the
consultant rather than on the project:

- ``consultants.cdm_user_id`` (-> ``users``, ``ON DELETE SET NULL``), filled
  from the tech lead of the project of each consultant's latest placement
  that had one;
- ``projects.tech_lead_user_id`` dropped;
- the role ``tech_lead`` becomes ``cdm`` on users, and the speaker and owner
  role ``tech_lead`` becomes ``cdm`` on signals, actions and the transcripts'
  speaker roles.

The downgrade puts the column back on projects, filled from the CDM of the
consultants placed on each project (the latest placement wins), and turns
``cdm`` back into ``tech_lead``.

Revision ID: 009
Revises: 008
Create Date: 2026-10-11 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES_NEW = "role IS NULL OR role IN ('pmo_manager', 'sme', 'cdm', 'ps', 'admin')"
ROLES_OLD = "role IS NULL OR role IN ('pmo_manager', 'sme', 'tech_lead', 'ps', 'admin')"
SPEAKERS_NEW = "('consultant', 'pmo_manager', 'sme', 'cdm', 'ps', 'other')"
SPEAKERS_OLD = "('consultant', 'pmo_manager', 'sme', 'tech_lead', 'ps', 'other')"


def _swap_role(old: str, new: str) -> None:
    """Rename a role value everywhere it is stored."""
    op.execute(f"UPDATE users SET role = '{new}' WHERE role = '{old}'")
    op.execute(
        f"UPDATE signals SET speaker_role = '{new}' WHERE speaker_role = '{old}'"
    )
    op.execute(f"UPDATE actions SET owner_role = '{new}' WHERE owner_role = '{old}'")
    # speaker_roles is {label: {"role": ..., "name": ...}}
    op.execute(
        f"""
        UPDATE session_transcripts t
        SET speaker_roles = (
            SELECT jsonb_object_agg(
                e.key,
                CASE WHEN e.value->>'role' = '{old}'
                     THEN jsonb_set(e.value, '{{role}}', '"{new}"')
                     ELSE e.value END
            )
            FROM jsonb_each(t.speaker_roles) AS e
        )
        WHERE t.speaker_roles IS NOT NULL
          AND jsonb_typeof(t.speaker_roles) = 'object'
          AND EXISTS (
              SELECT 1 FROM jsonb_each(t.speaker_roles) AS e
              WHERE e.value->>'role' = '{old}'
          )
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("consultants", sa.Column("cdm_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "consultants_cdm_user_id_fkey",
        "consultants",
        "users",
        ["cdm_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_consultants_cdm_user_id"),
        "consultants",
        ["cdm_user_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE consultants c
        SET cdm_user_id = (
            SELECT pr.tech_lead_user_id
            FROM placements p
            JOIN projects pr ON pr.id = p.project_id
            WHERE p.consultant_id = c.id AND pr.tech_lead_user_id IS NOT NULL
            ORDER BY p.start_date DESC, p.created_at DESC
            LIMIT 1
        )
        """
    )
    op.drop_index(op.f("ix_projects_tech_lead_user_id"), table_name="projects")
    op.drop_column("projects", "tech_lead_user_id")

    # Values change before the new checks, which would refuse 'tech_lead'
    for table, name in (
        ("users", "ck_users_role"),
        ("signals", "ck_signals_speaker_role"),
        ("actions", "ck_actions_owner_role"),
    ):
        op.drop_constraint(name, table, type_="check")
    _swap_role("tech_lead", "cdm")
    op.create_check_constraint("ck_users_role", "users", ROLES_NEW)
    op.create_check_constraint(
        "ck_signals_speaker_role", "signals", f"speaker_role IN {SPEAKERS_NEW}"
    )
    op.create_check_constraint(
        "ck_actions_owner_role", "actions", f"owner_role IN {SPEAKERS_NEW}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    for table, name in (
        ("users", "ck_users_role"),
        ("signals", "ck_signals_speaker_role"),
        ("actions", "ck_actions_owner_role"),
    ):
        op.drop_constraint(name, table, type_="check")
    _swap_role("cdm", "tech_lead")
    op.create_check_constraint("ck_users_role", "users", ROLES_OLD)
    op.create_check_constraint(
        "ck_signals_speaker_role", "signals", f"speaker_role IN {SPEAKERS_OLD}"
    )
    op.create_check_constraint(
        "ck_actions_owner_role", "actions", f"owner_role IN {SPEAKERS_OLD}"
    )

    op.add_column("projects", sa.Column("tech_lead_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "projects_tech_lead_user_id_fkey",
        "projects",
        "users",
        ["tech_lead_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_projects_tech_lead_user_id"),
        "projects",
        ["tech_lead_user_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE projects pr
        SET tech_lead_user_id = (
            SELECT c.cdm_user_id
            FROM placements p
            JOIN consultants c ON c.id = p.consultant_id
            WHERE p.project_id = pr.id AND c.cdm_user_id IS NOT NULL
            ORDER BY p.start_date DESC, p.created_at DESC
            LIMIT 1
        )
        """
    )
    op.drop_index(op.f("ix_consultants_cdm_user_id"), table_name="consultants")
    op.drop_constraint(
        "consultants_cdm_user_id_fkey", "consultants", type_="foreignkey"
    )
    op.drop_column("consultants", "cdm_user_id")
