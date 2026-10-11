"""Enumerations for users, the register, sessions, signals, issues, actions and health.

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
    # Consultant Director: the consultancy-side manager of the consultant.
    CDM = "cdm"
    PS = "ps"
    ADMIN = "admin"


# Roles that read every placement. The others read only the placements that
# name them (as placement specialist or SME) or whose consultant they manage
# (as the consultant's CDM).
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
    CDM = "cdm"
    PS = "ps"
    OTHER = "other"


# Who each role is, for the role-attribution prompt.
SPEAKER_ROLE_MEANINGS: dict[SpeakerRole, str] = {
    SpeakerRole.CONSULTANT: (
        "our contractor placed with the client; the call is about them"
    ),
    SpeakerRole.PMO_MANAGER: "owns project health across placements; escalates",
    SpeakerRole.SME: ("PMO subject-matter expert running onboarding or technical help"),
    SpeakerRole.CDM: (
        "Consultant Director: our consultancy-side manager of the consultant; "
        "mostly management, partly technical"
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
        "the same topic, blockers that outlast a session, an SME's or the "
        "CDM's view of their work"
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


class SignalIndicator(enum.StrEnum):
    """What a signal says outright that a critical trigger reads."""

    CLIENT_DISSATISFACTION = "client_dissatisfaction"
    CONSULTANT_CHANGE_REQUESTED = "consultant_change_requested"
    INTENT_TO_LEAVE = "intent_to_leave"


# What each indicator means, for the client and relationship/engagement prompts.
SIGNAL_INDICATOR_MEANINGS: dict[SignalIndicator, str] = {
    SignalIndicator.CLIENT_DISSATISFACTION: (
        "the client manager is unhappy with the consultant or their work, or "
        "has escalated about them"
    ),
    SignalIndicator.CONSULTANT_CHANGE_REQUESTED: (
        "the client has asked for, or talked about, a different consultant"
    ),
    SignalIndicator.INTENT_TO_LEAVE: (
        "the consultant talks of leaving, another offer, or not wanting to continue"
    ),
}

# The indicators each extraction may set: the client node reads the client's
# view, the relationship/engagement node the consultant's intent to stay.
# Its prompt lists only these, and emit clears any other.
SIGNAL_INDICATORS_BY_CATEGORY: dict[SignalCategory, tuple[SignalIndicator, ...]] = {
    SignalCategory.ISSUE: (),
    SignalCategory.RELATIONSHIP_ENGAGEMENT: (SignalIndicator.INTENT_TO_LEAVE,),
    SignalCategory.CLIENT: (
        SignalIndicator.CLIENT_DISSATISFACTION,
        SignalIndicator.CONSULTANT_CHANGE_REQUESTED,
    ),
}


class RiskLevel(enum.StrEnum):
    """A placement's RAG level from its overall score (PRD, "Scoring rules")."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class Trend(enum.StrEnum):
    """Change in the overall score over the trend window."""

    UP = "up"
    FLAT = "flat"
    DOWN = "down"


class RiskTrigger(enum.StrEnum):
    """The PRD's early-warning triggers; each opens a risk flag."""

    GONE_QUIET = "gone_quiet"
    CLIENT_DISSATISFACTION = "client_dissatisfaction"
    REPEATED_BLOCKER = "repeated_blocker"
    DOWNWARD_TREND = "downward_trend"
    RELATIONSHIP_STRAIN = "relationship_strain"
    CONTRACT_HORIZON = "contract_horizon"
    INTENT_TO_LEAVE = "intent_to_leave"
    MISSED_COMMITMENT = "missed_commitment"


# When each trigger fires (PRD, "Early-warning triggers"); the thresholds are
# the health configuration's.
RISK_TRIGGER_MEANINGS: dict[RiskTrigger, str] = {
    RiskTrigger.GONE_QUIET: "no post from the consultant in the group for a while",
    RiskTrigger.CLIENT_DISSATISFACTION: (
        "the client manager is unhappy, escalated, or asked for a change of consultant"
    ),
    RiskTrigger.REPEATED_BLOCKER: (
        "the same technical blocker came up in two calls or has stayed open too long"
    ),
    RiskTrigger.DOWNWARD_TREND: "the overall score fell sharply over the trend window",
    RiskTrigger.RELATIONSHIP_STRAIN: (
        "a serious negative relationship signal, or two notable ones close together"
    ),
    RiskTrigger.CONTRACT_HORIZON: (
        "the expected end is close or past and the extension is not confirmed"
    ),
    RiskTrigger.INTENT_TO_LEAVE: (
        "the consultant mentioned leaving, another offer, or not wanting to continue"
    ),
    RiskTrigger.MISSED_COMMITMENT: (
        "an action the consultant owned passed its due date without an update"
    ),
}


class FlagSeverity(enum.StrEnum):
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Each trigger's severity (PRD, "Early-warning triggers"). An open critical
# flag keeps its placement at least amber.
RISK_TRIGGER_SEVERITY: dict[RiskTrigger, FlagSeverity] = {
    RiskTrigger.GONE_QUIET: FlagSeverity.MEDIUM,
    RiskTrigger.CLIENT_DISSATISFACTION: FlagSeverity.CRITICAL,
    RiskTrigger.REPEATED_BLOCKER: FlagSeverity.HIGH,
    RiskTrigger.DOWNWARD_TREND: FlagSeverity.HIGH,
    RiskTrigger.RELATIONSHIP_STRAIN: FlagSeverity.HIGH,
    RiskTrigger.CONTRACT_HORIZON: FlagSeverity.HIGH,
    RiskTrigger.INTENT_TO_LEAVE: FlagSeverity.CRITICAL,
    RiskTrigger.MISSED_COMMITMENT: FlagSeverity.MEDIUM,
}


class SnapshotReason(enum.StrEnum):
    """What caused a health recompute."""

    CALL = "call"  # a call was analysed
    REGISTER = "register"  # the placement or its project was edited
    DAILY = "daily"  # the daily recompute
    CATCH_UP = "catch_up"  # a takeover found the latest snapshot out of date


class HealthView(enum.StrEnum):
    """How much of a placement's health a reader sees (BACKLOG #5)."""

    FULL = "full"  # every dimension, overall, level, trend and flags
    TECHNICAL = "technical"  # an SME: the Technical score and its trend only


def check_in(column: str, values: type[enum.StrEnum]) -> str:
    """SQL for a CHECK constraint limiting ``column`` to ``values``."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"
