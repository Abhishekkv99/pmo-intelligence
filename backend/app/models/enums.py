"""Enumerations for users, the register, sessions, signals, issues and actions.

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


# What each kind of call is, for the classify prompt.
SESSION_KIND_MEANINGS: dict[SessionKind, str] = {
    SessionKind.ONBOARDING: (
        "help in the first weeks: access, laptop, environment, process, people"
    ),
    SessionKind.TECHNICAL: "help with the technical work of the role",
    SessionKind.CHECK_IN: "a regular call on progress, the team and how it is going",
    SessionKind.ESCALATION: (
        "a problem with the client, the work or the consultant that needs "
        "someone to step in"
    ),
    SessionKind.OTHER: "none of the above",
}


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


class SpeakerRole(enum.StrEnum):
    """Who a diarized speaker (or a chat author) is, as role attribution decides."""

    CONSULTANT = "consultant"
    PMO_MANAGER = "pmo_manager"
    SME = "sme"
    TECH_LEAD = "tech_lead"
    PS = "ps"
    OTHER = "other"


# Who each role is, for the role-attribution prompt.
SPEAKER_ROLE_MEANINGS: dict[SpeakerRole, str] = {
    SpeakerRole.CONSULTANT: (
        "our contractor placed with the client; the call is about them"
    ),
    SpeakerRole.PMO_MANAGER: "owns project health across placements; escalates",
    SpeakerRole.SME: ("PMO subject-matter expert running onboarding or technical help"),
    SpeakerRole.TECH_LEAD: (
        "our tech lead reviewing the consultant's technical delivery"
    ),
    SpeakerRole.PS: (
        "placement specialist who placed the consultant; owns the client "
        "relationship and extensions"
    ),
    SpeakerRole.OTHER: "anyone else, or a speaker whose role is unclear",
}


class Dimension(enum.StrEnum):
    """The six health dimensions a signal counts towards."""

    DELIVERY = "delivery"
    TECHNICAL = "technical"
    RELATIONSHIP = "relationship"
    ENGAGEMENT = "engagement"
    ONBOARDING = "onboarding"
    COMMUNICATION = "communication"


# What each dimension measures, for the prompts (PRD, "The project health model").
DIMENSION_MEANINGS: dict[Dimension, str] = {
    Dimension.DELIVERY: (
        "Is the consultant delivering what the client expects, on time: missed "
        "deadlines, rework, the client asking again, praise for a shipped piece"
    ),
    Dimension.TECHNICAL: (
        "Can they do the technical work of the role: repeated help requests on "
        "the same topic, blockers that outlast a session, the tech lead's view"
    ),
    Dimension.RELATIONSHIP: (
        "Chemistry with the team, the manager and superiors: how they describe "
        "the manager, conflict, exclusion from meetings, friction others note"
    ),
    Dimension.ENGAGEMENT: (
        "Morale, confidence, intent to stay: tone, talk of leaving, stress, enthusiasm"
    ),
    Dimension.ONBOARDING: (
        "Access, environment, process and people set up in the first weeks: "
        "open access requests, no laptop, no buddy"
    ),
    Dimension.COMMUNICATION: (
        "Are they visible: updates posted, questions asked, stand-ups attended, "
        "stakeholder questions left unanswered"
    ),
}


class Polarity(enum.StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


# A signal's severity: how strongly it bears on its dimension.
SEVERITY_MIN = 1
SEVERITY_MAX = 3
SEVERITY_MEANINGS: dict[int, str] = {
    1: "minor: worth noting, little effect on its own",
    2: "notable: affects the placement if it continues",
    3: "serious: puts the placement at risk now",
}


class SourceKind(enum.StrEnum):
    """What a signal or an action was read from."""

    SESSION = "session"
    MESSAGE = "message"


class SignalCategory(enum.StrEnum):
    """Which extraction produced a signal."""

    ISSUE = "issue"
    RELATIONSHIP_ENGAGEMENT = "relationship_engagement"
    CLIENT = "client"


class IssueStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ActionStatus(enum.StrEnum):
    OPEN = "open"
    DONE = "done"
    OVERDUE = "overdue"


def check_in(column: str, values: type[enum.StrEnum]) -> str:
    """SQL for a CHECK constraint limiting ``column`` to ``values``."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"
