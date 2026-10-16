"""The analysis step against a real database, with the pipeline faked.

What the pipeline is given (transcript, names, earlier issues and open
actions) and how its result is stored in one go: transcript fields, the
session's kind, signals at their moment, issues linked or new, actions with
their owner, earlier actions closed, costs, and a failed session when the
run produced nothing usable.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.session import nodes
from app.ai.session.drafts import (
    ActionDraft,
    IssueDraft,
    SessionAnalysis,
    SignalDraft,
)
from app.ai.session.graph import SessionRunResult
from app.ai.session.state import SessionContext
from app.models.enums import (
    ActionStatus,
    IssueStatus,
    JobStatus,
    Role,
    SessionStatus,
    SpeakerRole,
)
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session, SessionTranscript
from app.models.signal import Action, Issue, Signal
from app.models.user import User
from app.services.session_analysis import NOTHING_USABLE, SessionAnalysisService
from tests.unit.session_pipeline_helpers import UTTERANCES as HELPER_UTTERANCES
from tests.unit.session_pipeline_helpers import FakeModel

# 23:30 UTC on 5 October is 00:30 on 6 October in London (BST).
HELD_AT = datetime(2026, 10, 5, 23, 30, tzinfo=UTC)
UTTERANCES = [
    {"speaker": "A", "text": "Morning.", "start_ms": 0, "end_ms": 900},
    {"speaker": "B", "text": "Still no staging access.", "start_ms": 61_000},
]
COST = {
    "service": "azure_openai",
    "operation": "session_summarise",
    "amount_usd": 0.002,
    "input_tokens": 1_000,
    "output_tokens": 200,
    "model": "gpt-5.4-mini-test",
    "duration_seconds": 3.5,
}


class Placed:
    """A placement with an SME, a transcribed session and its running job."""

    def __init__(
        self,
        placement: Placement,
        sme: User,
        session: Session,
        job: ProcessingJob,
    ) -> None:
        self.placement = placement
        self.sme = sme
        self.session = session
        self.job = job


@pytest.fixture
async def placed(db_session: AsyncSession) -> Placed:
    client = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
    consultant = Consultant(full_name="Priya Shah")
    sme = User(
        email=f"sam-{uuid.uuid4()}@example.com",
        full_name="Sam Okafor",
        role=Role.SME.value,
    )
    db_session.add_all([client, consultant, sme])
    await db_session.flush()
    project = Project(
        client_id=client.id, name="Data platform", client_manager_name="Dana Lee"
    )
    db_session.add(project)
    await db_session.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date(2026, 9, 1),
        sme_user_id=sme.id,
    )
    db_session.add(placement)
    await db_session.flush()
    session = Session(
        placement_id=placement.id,
        held_at=HELD_AT,
        source="upload",
        status=SessionStatus.ANALYZING.value,
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        SessionTranscript(
            session_id=session.id,
            full_text="Morning. Still no staging access.",
            utterances=UTTERANCES,
        )
    )
    job = ProcessingJob(
        kind="session",
        subject_id=session.id,
        status=JobStatus.IN_PROGRESS.value,
        stage="analyzing",
    )
    db_session.add(job)
    await db_session.flush()
    return Placed(placement, sme, session, job)


def _signal(**changes: object) -> SignalDraft:
    values: dict[str, object] = {
        "category": "issue",
        "dimension": "technical",
        "polarity": "negative",
        "severity": 2,
        "confidence": 0.9,
        "quote": "Still no staging access.",
        "note": "Blocked again.",
        "speaker_role": "consultant",
        "offset_ms": 61_000,
    }
    values.update(changes)
    return SignalDraft(**values)  # type: ignore[arg-type]


class FakePipeline:
    def __init__(
        self,
        analysis: SessionAnalysis | None = None,
        *,
        succeeded: list[str] | None = None,
        node_errors: list[dict[str, object]] | None = None,
    ) -> None:
        self.analysis = analysis or SessionAnalysis(summary="A short call.")
        self.succeeded = ["summarise"] if succeeded is None else succeeded
        self.node_errors = node_errors or []
        self.contexts: list[SessionContext] = []

    async def __call__(self, context: SessionContext) -> SessionRunResult:
        self.contexts.append(context)
        return SessionRunResult(
            analysis=self.analysis,
            cost_records=[dict(COST)],
            node_errors=list(self.node_errors),
            succeeded=self.succeeded,
        )


async def _analyse(db: AsyncSession, placed: Placed, pipeline: FakePipeline) -> None:
    await SessionAnalysisService(db, pipeline=pipeline).analyse(
        placed.session, placed.job
    )
    await db.refresh(placed.session)
    await db.refresh(placed.job)


async def _issue(db: AsyncSession, placed: Placed, **fields: object) -> Issue:
    values: dict[str, object] = {
        "placement_id": placed.placement.id,
        "topic": "no staging access",
        "first_seen_at": HELD_AT - timedelta(days=14),
        "last_seen_at": HELD_AT - timedelta(days=14),
    }
    values.update(fields)
    issue = Issue(**values)
    db.add(issue)
    await db.flush()
    return issue


async def _action(db: AsyncSession, placed: Placed, **fields: object) -> Action:
    values: dict[str, object] = {
        "placement_id": placed.placement.id,
        "source_kind": "session",
        "source_id": uuid.uuid4(),
        "owner_role": "sme",
        "description": "Order a laptop",
        "quote": "I'll order your laptop",
    }
    values.update(fields)
    action = Action(**values)
    db.add(action)
    await db.flush()
    return action


class TestContext:
    async def test_the_pipeline_gets_the_transcript_names_and_uk_call_day(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        pipeline = FakePipeline()

        await _analyse(db_session, placed, pipeline)

        [context] = pipeline.contexts
        assert context.utterances == UTTERANCES
        assert context.consultant_name == "Priya Shah"
        assert context.client_name == "Acme"
        assert context.project_name == "Data platform"
        assert context.client_manager_name == "Dana Lee"
        assert context.people == {SpeakerRole.SME: "Sam Okafor"}
        assert context.call_day == date(2026, 10, 6)

    async def test_open_and_recently_resolved_issues_and_open_actions_are_offered(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        open_issue = await _issue(db_session, placed)
        recent = await _issue(
            db_session,
            placed,
            topic="no VPN",
            first_seen_at=HELD_AT - timedelta(days=13),
            status=IssueStatus.RESOLVED.value,
            resolved_at=HELD_AT - timedelta(days=10),
        )
        await _issue(
            db_session,
            placed,
            topic="no badge",
            status=IssueStatus.RESOLVED.value,
            resolved_at=HELD_AT - timedelta(days=45),
        )
        open_action = await _action(db_session, placed)
        await _action(db_session, placed, status=ActionStatus.DONE.value)
        pipeline = FakePipeline()

        await _analyse(db_session, placed, pipeline)

        [context] = pipeline.contexts
        offered = {(i.ref, i.issue_id) for i in context.earlier_issues}
        assert offered == {("I1", open_issue.id), ("I2", recent.id)}
        assert [(a.ref, a.action_id) for a in context.open_actions] == [
            ("A1", open_action.id)
        ]

    async def test_a_session_without_a_transcript_cannot_be_analysed(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        transcript = await db_session.scalar(
            select(SessionTranscript).where(
                SessionTranscript.session_id == placed.session.id
            )
        )
        await db_session.delete(transcript)
        await db_session.flush()

        with pytest.raises(ValueError, match="no transcript"):
            await SessionAnalysisService(db_session, pipeline=FakePipeline()).analyse(
                placed.session, placed.job
            )


class TestStore:
    async def test_a_usable_run_is_stored_and_the_session_completed(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        analysis = SessionAnalysis(
            speaker_roles={"B": {"role": "consultant", "name": "Priya Shah"}},
            session_class="technical",
            project_phase="fifth week",
            summary="Priya is still blocked.",
            signals=[
                _signal(category="relationship_engagement", indicator="intent_to_leave")
            ],
            quotes_rejected=2,
        )
        errors = [{"node": "client_signals", "error": "boom", "duration_seconds": 1}]
        pipeline = FakePipeline(analysis, node_errors=errors)

        await _analyse(db_session, placed, pipeline)

        session = placed.session
        assert session.status == SessionStatus.COMPLETED.value
        assert session.kind == "technical"
        assert session.quotes_rejected == 2
        assert session.node_errors == errors
        assert placed.job.status == JobStatus.COMPLETED.value
        assert placed.job.completed_at is not None

        transcript = await db_session.scalar(
            select(SessionTranscript).where(SessionTranscript.session_id == session.id)
        )
        assert transcript is not None
        await db_session.refresh(transcript)
        assert transcript.summary == "Priya is still blocked."
        assert transcript.session_class == "technical"
        assert transcript.project_phase == "fifth week"
        assert transcript.speaker_roles == {
            "B": {"role": "consultant", "name": "Priya Shah"}
        }

        [signal] = (
            await db_session.scalars(
                select(Signal).where(Signal.source_id == session.id)
            )
        ).all()
        assert signal.placement_id == placed.placement.id
        assert signal.source_kind == "session"
        assert signal.offset_ms == 61_000
        assert signal.occurred_at == HELD_AT + timedelta(seconds=61)
        assert signal.speaker_role == "consultant"
        assert signal.issue_id is None
        assert signal.indicator == "intent_to_leave"

        [cost] = (
            await db_session.scalars(
                select(ProcessingCost).where(ProcessingCost.session_id == session.id)
            )
        ).all()
        assert cost.operation == "session_summarise"
        assert cost.processing_job_id == placed.job.id
        assert cost.input_tokens == 1_000

    async def test_a_kind_set_by_a_person_is_kept(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        placed.session.kind = "escalation"
        placed.session.kind_overridden_by_user_id = placed.sme.id
        await db_session.flush()

        await _analyse(
            db_session, placed, FakePipeline(SessionAnalysis(session_class="check_in"))
        )

        assert placed.session.kind == "escalation"

    async def test_a_new_issue_is_created_with_its_signal(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        analysis = SessionAnalysis(
            issues=[
                IssueDraft(
                    topic="no staging access",
                    earlier_issue_id=None,
                    resolved_by_end=False,
                    signal=_signal(),
                )
            ]
        )

        await _analyse(db_session, placed, FakePipeline(analysis))

        [issue] = (
            await db_session.scalars(
                select(Issue).where(Issue.placement_id == placed.placement.id)
            )
        ).all()
        assert issue.status == IssueStatus.OPEN.value
        assert issue.occurrence_count == 1
        assert issue.first_seen_at == HELD_AT
        assert issue.last_seen_at == HELD_AT
        signal = await db_session.scalar(
            select(Signal).where(Signal.issue_id == issue.id)
        )
        assert signal is not None

    async def test_a_linked_issue_is_counted_once_per_call_and_seen_again(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        earlier = await _issue(db_session, placed)
        draft = IssueDraft(
            topic="staging access",
            earlier_issue_id=earlier.id,
            resolved_by_end=False,
            signal=_signal(),
        )
        second = IssueDraft(
            topic="staging",
            earlier_issue_id=earlier.id,
            resolved_by_end=False,
            signal=_signal(dimension="onboarding"),
        )

        await _analyse(
            db_session, placed, FakePipeline(SessionAnalysis(issues=[draft, second]))
        )

        await db_session.refresh(earlier)
        assert earlier.occurrence_count == 2
        assert earlier.last_seen_at == HELD_AT
        assert earlier.topic == "no staging access"
        signals = (
            await db_session.scalars(
                select(Signal).where(Signal.issue_id == earlier.id)
            )
        ).all()
        assert len(signals) == 2

    async def test_a_resolved_issue_raised_again_reopens(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        earlier = await _issue(
            db_session,
            placed,
            status=IssueStatus.RESOLVED.value,
            resolved_at=HELD_AT - timedelta(days=7),
        )
        draft = IssueDraft(
            topic="staging access",
            earlier_issue_id=earlier.id,
            resolved_by_end=False,
            signal=_signal(),
        )

        await _analyse(
            db_session, placed, FakePipeline(SessionAnalysis(issues=[draft]))
        )

        await db_session.refresh(earlier)
        assert earlier.status == IssueStatus.OPEN.value
        assert earlier.resolved_at is None

    async def test_an_issue_resolved_by_the_end_of_the_call_is_closed(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        earlier = await _issue(db_session, placed)
        draft = IssueDraft(
            topic="staging access",
            earlier_issue_id=earlier.id,
            resolved_by_end=True,
            signal=_signal(polarity="positive"),
        )

        await _analyse(
            db_session, placed, FakePipeline(SessionAnalysis(issues=[draft]))
        )

        await db_session.refresh(earlier)
        assert earlier.status == IssueStatus.RESOLVED.value
        assert earlier.resolved_at == HELD_AT

    async def test_an_older_call_does_not_reopen_an_issue_resolved_since(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        later = HELD_AT + timedelta(days=3)
        earlier = await _issue(
            db_session,
            placed,
            last_seen_at=later,
            status=IssueStatus.RESOLVED.value,
            resolved_at=later,
        )
        draft = IssueDraft(
            topic="staging access",
            earlier_issue_id=earlier.id,
            resolved_by_end=False,
            signal=_signal(),
        )

        await _analyse(
            db_session, placed, FakePipeline(SessionAnalysis(issues=[draft]))
        )

        await db_session.refresh(earlier)
        assert earlier.status == IssueStatus.RESOLVED.value
        assert earlier.last_seen_at == later
        assert earlier.occurrence_count == 2

    async def test_actions_get_their_owner_from_the_placement(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        def draft(role: str) -> ActionDraft:
            return ActionDraft(
                description=f"{role} does it",
                owner_role=role,
                due_text="by Friday",
                due_date=date(2026, 10, 9),
                quote="Still no staging access.",
                offset_ms=61_000,
            )

        analysis = SessionAnalysis(
            actions=[draft("sme"), draft("consultant"), draft("ps")]
        )

        await _analyse(db_session, placed, FakePipeline(analysis))

        actions = (
            await db_session.scalars(
                select(Action).where(Action.source_id == placed.session.id)
            )
        ).all()
        owners = {a.owner_role: a.owner_user_id for a in actions}
        assert owners == {"sme": placed.sme.id, "consultant": None, "ps": None}
        assert all(a.status == ActionStatus.OPEN.value for a in actions)
        assert all(a.due_date == date(2026, 10, 9) for a in actions)

    async def test_the_consultants_cdm_is_named_and_owns_cdm_actions(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        cdm = User(
            email=f"cara-{uuid.uuid4()}@example.com",
            full_name="Cara Doyle",
            role=Role.CDM.value,
        )
        db_session.add(cdm)
        await db_session.flush()
        consultant = await db_session.get(Consultant, placed.placement.consultant_id)
        assert consultant is not None
        consultant.cdm_user_id = cdm.id
        await db_session.flush()
        pipeline = FakePipeline(
            SessionAnalysis(
                actions=[
                    ActionDraft(
                        description="Speak to the client manager",
                        owner_role="cdm",
                        due_text="next week",
                        due_date=None,
                        quote="Still no staging access.",
                        offset_ms=61_000,
                    )
                ]
            )
        )

        await _analyse(db_session, placed, pipeline)

        [context] = pipeline.contexts
        assert context.people == {
            SpeakerRole.SME: "Sam Okafor",
            SpeakerRole.CDM: "Cara Doyle",
        }
        action = (
            await db_session.scalars(
                select(Action).where(Action.source_id == placed.session.id)
            )
        ).one()
        assert action.owner_user_id == cdm.id

    async def test_an_earlier_action_the_call_closed_is_done(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        earlier = await _action(db_session, placed)
        analysis = SessionAnalysis(closed_action_ids=[earlier.id])

        await _analyse(db_session, placed, FakePipeline(analysis))

        await db_session.refresh(earlier)
        assert earlier.status == ActionStatus.DONE.value
        assert earlier.closed_at == HELD_AT
        assert earlier.closed_source_id == placed.session.id


class TestNothingUsable:
    async def test_the_session_fails_and_keeps_only_costs_and_errors(
        self, db_session: AsyncSession, placed: Placed
    ) -> None:
        errors = [{"node": "summarise", "error": "boom", "duration_seconds": 1}]
        analysis = SessionAnalysis(
            session_class="check_in", signals=[_signal(category="client")]
        )
        pipeline = FakePipeline(
            analysis, succeeded=["attribute_roles", "classify"], node_errors=errors
        )

        await _analyse(db_session, placed, pipeline)

        session = placed.session
        assert session.status == SessionStatus.FAILED.value
        assert session.error_message == NOTHING_USABLE
        assert session.node_errors == errors
        assert session.kind is None
        assert placed.job.status == JobStatus.FAILED.value
        assert placed.job.error_message == NOTHING_USABLE
        assert (
            await db_session.scalar(
                select(Signal).where(Signal.source_id == session.id)
            )
            is None
        )
        cost = await db_session.scalar(
            select(ProcessingCost).where(ProcessingCost.session_id == session.id)
        )
        assert cost is not None


class TestTranscriptToSignals:
    async def test_the_real_graph_with_a_faked_model_stores_verified_signals(
        self,
        db_session: AsyncSession,
        placed: Placed,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(nodes, "invoke_structured", FakeModel())
        transcript = await db_session.scalar(
            select(SessionTranscript).where(
                SessionTranscript.session_id == placed.session.id
            )
        )
        assert transcript is not None
        transcript.utterances = HELPER_UTTERANCES
        transcript.full_text = " ".join(str(u["text"]) for u in HELPER_UTTERANCES)
        staging = await _issue(db_session, placed)
        laptop = await _action(db_session, placed)

        await SessionAnalysisService(db_session).analyse(placed.session, placed.job)

        await db_session.refresh(placed.session)
        assert placed.session.status == SessionStatus.COMPLETED.value
        assert placed.session.kind == "check_in"
        assert placed.session.quotes_rejected == 0
        signals = (
            await db_session.scalars(
                select(Signal).where(Signal.source_id == placed.session.id)
            )
        ).all()
        assert {
            (s.category, s.dimension, s.speaker_role, s.offset_ms, s.indicator)
            for s in signals
        } == {
            ("issue", "technical", "consultant", 5_000, None),
            ("client", "delivery", "consultant", 5_000, "client_dissatisfaction"),
            ("relationship_engagement", "relationship", "consultant", 12_000, None),
        }
        assert len(signals) == 3
        await db_session.refresh(staging)
        assert staging.occurrence_count == 2
        [action] = (
            await db_session.scalars(
                select(Action).where(Action.source_id == placed.session.id)
            )
        ).all()
        assert action.owner_user_id == placed.sme.id
        assert action.offset_ms == 20_000
        await db_session.refresh(laptop)
        assert laptop.status == ActionStatus.DONE.value
        costs = (
            await db_session.scalars(
                select(ProcessingCost).where(
                    ProcessingCost.session_id == placed.session.id
                )
            )
        ).all()
        assert len(costs) == 7
