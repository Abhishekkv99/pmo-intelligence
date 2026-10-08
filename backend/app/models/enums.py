"""Enumerations for users and the placement register.

The single source for these value sets: models, migrations, schemas, tests and
docs cite them from here rather than repeating the strings. Values are stored
as plain strings with a CHECK constraint (``check_in``) so the database
rejects anything outside the set.
"""

import enum


class Role(enum.StrEnum):
    """What a user may see. ``NULL`` on the row means no access yet."""

    PMO_MANAGER = "pmo_manager"
    SME = "sme"
    TECH_LEAD = "tech_lead"
    PS = "ps"
    ADMIN = "admin"


# Roles that read every placement. The others read only the placements that
# name them (as placement specialist, SME, or the project's tech lead).
GLOBAL_ROLES: frozenset[Role] = frozenset({Role.PMO_MANAGER, Role.ADMIN})


class ConsultantStatus(enum.StrEnum):
    BENCH = "bench"
    PLACED = "placed"
    LEFT = "left"


class ExtensionStatus(enum.StrEnum):
    NOT_DUE = "not_due"
    DUE = "due"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class PlacementStatus(enum.StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
    TERMINATED = "terminated"


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionKind(enum.StrEnum):
    """What a recorded PMO call was; set by the pipeline, correctable by a person."""

    ONBOARDING = "onboarding"
    TECHNICAL = "technical"
    CHECK_IN = "check_in"
    ESCALATION = "escalation"
    OTHER = "other"


class SessionSource(enum.StrEnum):
    """Where a session's recording came from."""

    S3 = "s3"
    UPLOAD = "upload"
    URL = "url"
    GRAPH = "graph"


class SessionStatus(enum.StrEnum):
    """uploaded → transcribing → transcribed → analyzing → completed / failed."""

    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class FolderMatchStatus(enum.StrEnum):
    """How a recordings folder was tied to a consultant.

    The scanner re-matches only ``needs_choice`` and ``unmatched`` folders; a
    folder a person ``chosen`` is never overwritten.
    """

    MATCHED = "matched"
    CHOSEN = "chosen"
    NEEDS_CHOICE = "needs_choice"
    UNMATCHED = "unmatched"


class ScanStatus(enum.StrEnum):
    """How a pass over the recordings folder ended (``running`` until it does)."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def check_in(column: str, values: type[enum.StrEnum]) -> str:
    """SQL for a CHECK constraint limiting ``column`` to ``values``."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"
