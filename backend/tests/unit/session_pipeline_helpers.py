"""A session-pipeline context and model answers shared by the pipeline tests."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel

from app.ai.session.prompts import (
    actions,
    classify,
    client_signals,
    issues,
    relationship_engagement,
    roles,
    summarise,
)
from app.ai.session.schemas import (
    ActionsResult,
    ClassificationResult,
    ClosedAction,
    ExtractedAction,
    ExtractedIssue,
    ExtractedSignal,
    IssuesResult,
    RoleAttributionResult,
    SignalsResult,
    SpeakerAssignment,
    SummaryResult,
)
from app.ai.session.state import ActionRef, IssueRef, SessionContext
from app.ai.structured import LLMUsage
from app.models.enums import (
    Dimension,
    IssueStatus,
    Polarity,
    SessionKind,
    SpeakerRole,
)

HELD_AT = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)
EARLIER_ISSUE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
OPEN_ACTION_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b1")

UTTERANCES = [
    {"speaker": "A", "text": "Morning Priya, how are things?", "start_ms": 0},
    {
        "speaker": "B",
        "text": "I still can't get into the staging cluster. "
        "The client manager said she was disappointed with the sprint.",
        "start_ms": 5_000,
    },
    {
        "speaker": "B",
        "text": "To be honest I'm enjoying the team a lot.",
        "start_ms": 12_000,
    },
    {
        "speaker": "A",
        "text": "I'll chase the platform team by Friday. Your laptop request is "
        "sorted now.",
        "start_ms": 20_000,
    },
]


def context(**changes: object) -> SessionContext:
    values: dict[str, object] = {
        "held_at": HELD_AT,
        "call_day": date(2026, 10, 6),
        "consultant_name": "Priya Shah",
        "client_name": "Acme",
        "project_name": "Data platform",
        "client_manager_name": "Dana Lee",
        "people": {SpeakerRole.SME: "Sam Okafor"},
        "utterances": UTTERANCES,
        "full_text": " ".join(str(u["text"]) for u in UTTERANCES),
        "earlier_issues": [
            IssueRef(
                ref="I1",
                issue_id=EARLIER_ISSUE_ID,
                topic="no staging access",
                status=IssueStatus.OPEN.value,
                first_seen=date(2026, 9, 22),
                occurrence_count=1,
            )
        ],
        "open_actions": [
            ActionRef(
                ref="A1",
                action_id=OPEN_ACTION_ID,
                description="Order a laptop",
                owner_role=SpeakerRole.SME.value,
                due_text=None,
            )
        ],
    }
    values.update(changes)
    return SessionContext(**values)  # type: ignore[arg-type]


def signal(quote: str, **changes: object) -> ExtractedSignal:
    values: dict[str, object] = {
        "dimension": Dimension.RELATIONSHIP,
        "polarity": Polarity.POSITIVE,
        "severity": 2,
        "confidence": 0.8,
        "quote": quote,
        "note": "Likes the team.",
    }
    values.update(changes)
    return ExtractedSignal.model_validate(values)


ROLES = RoleAttributionResult(
    speakers=[
        SpeakerAssignment(speaker="A", role=SpeakerRole.SME, name="Sam Okafor"),
        SpeakerAssignment(speaker="B", role=SpeakerRole.CONSULTANT, name="Priya Shah"),
    ],
    confidence=0.9,
    rationale="B reports progress; A offers help.",
)
CLASSIFICATION = ClassificationResult(
    session_class=SessionKind.CHECK_IN, project_phase="third week"
)
SUMMARY = SummaryResult(summary="Priya is blocked on staging access.")
ISSUES = IssuesResult(
    issues=[
        ExtractedIssue(
            topic="no staging access",
            earlier_issue="I1",
            resolved_by_end=False,
            dimension=Dimension.TECHNICAL,
            polarity=Polarity.NEGATIVE,
            severity=2,
            confidence=0.9,
            quote="I still can't get into the staging cluster.",
            note="Blocked for a second call.",
        )
    ]
)
RELATIONSHIP = SignalsResult(
    signals=[signal("To be honest I'm enjoying the team a lot.")]
)
CLIENT = SignalsResult(
    signals=[
        signal(
            "The client manager said she was disappointed with the sprint.",
            dimension=Dimension.DELIVERY,
            polarity=Polarity.NEGATIVE,
            severity=3,
        )
    ]
)
ACTIONS = ActionsResult(
    actions=[
        ExtractedAction(
            description="Chase the platform team for staging access",
            owner_role=SpeakerRole.SME,
            due_text="by Friday",
            due_date="2026-10-09",
            quote="I'll chase the platform team by Friday.",
        )
    ],
    closed=[ClosedAction(action="A1", quote="Your laptop request is sorted now.")],
)

# Each node's system prompt → (node name, the model's answer).
ANSWERS: dict[str, tuple[str, BaseModel]] = {
    roles.SYSTEM: ("attribute_roles", ROLES),
    classify.SYSTEM: ("classify", CLASSIFICATION),
    summarise.SYSTEM: ("summarise", SUMMARY),
    issues.SYSTEM: ("issues", ISSUES),
    relationship_engagement.SYSTEM: ("relationship_engagement", RELATIONSHIP),
    client_signals.SYSTEM: ("client_signals", CLIENT),
    actions.SYSTEM: ("actions", ACTIONS),
}


class FakeModel:
    """Answers each node from ANSWERS; the nodes in ``failing`` raise."""

    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.prompts: dict[str, str] = {}

    async def __call__(
        self, schema: type[BaseModel], system: str, user: str, **kwargs: Any
    ) -> tuple[BaseModel, LLMUsage]:
        name, answer = ANSWERS[system]
        self.prompts[name] = user
        if name in self.failing:
            raise RuntimeError(f"{name} unavailable")
        assert isinstance(answer, schema)
        return answer, LLMUsage(input_tokens=100, output_tokens=10)
