"""The analysis step of the ``session`` job: run the pipeline, store its result.

The pipeline graph touches no database. This service loads what it needs
(the transcript, the register's names, the placement's earlier issues and
open actions), runs it, and stores everything it produced at once, so a
failed run leaves nothing half-written and a retry starts clean.

What is stored:
- on the transcript: the summary, the class, the project phase and the
  speaker roles; the class becomes the session's kind unless a person set it;
- the signals, each at the call's time plus its offset in the recording;
- the issues: an issue the model linked to an earlier one raises that one's
  count (once per call) and last-seen time, reopens it if it was resolved,
  and closes it when the call resolved it; any other is a new issue;
- the actions, with the placement's PS, SME or tech lead as owner when the
  owner role names them, and the earlier actions the call closed;
- a cost row per LLM call, the node errors and the rejected-quote count.

A run where neither the summary nor any extraction succeeded is useless: the
session is failed (costs and node errors are kept) so a person retries it.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.session.drafts import SignalDraft
from app.ai.session.graph import SessionRunResult, run_session_pipeline
from app.ai.session.state import ActionRef, IssueRef, SessionContext
from app.config import settings
from app.db.repositories.placement_repo import PlacementRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.signal_repo import SignalRepository
from app.models.enums import (
    ActionStatus,
    IssueStatus,
    JobStatus,
    SessionStatus,
    SourceKind,
    SpeakerRole,
)
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.session import Session
from app.models.signal import Action, Issue, Signal
from app.services.recordings.folder_names import local_day

logger = logging.getLogger(__name__)

NOTHING_USABLE = (
    "Analysis produced nothing: the summary and every extraction failed; retry it"
)

Pipeline = Callable[[SessionContext], Awaitable[SessionRunResult]]


@dataclass(frozen=True)
class _Loaded:
    context: SessionContext
    # The user each owner role names on this placement.
    owners: dict[str, uuid.UUID]


def _person(name: str | None, email: str) -> str:
    return name or email


class SessionAnalysisService:
    def __init__(self, db: AsyncSession, *, pipeline: Pipeline | None = None) -> None:
        self.db = db
        self.sessions = SessionRepository(db)
        self.placements = PlacementRepository(db)
        self.signals = SignalRepository(db)
        self._pipeline = pipeline or run_session_pipeline

    async def analyse(self, session: Session, job: ProcessingJob) -> None:
        """Run the pipeline on a transcribed session and store the result."""
        loaded = await self._load(session)
        result = await self._pipeline(loaded.context)
        await self._store(session, job, loaded, result)

    async def _load(self, session: Session) -> _Loaded:
        transcript = await self.sessions.get_transcript(session.id)
        if transcript is None:
            raise ValueError("The session has no transcript to analyse")
        row = await self.placements.get_row(session.placement_id)
        if row is None:
            raise ValueError("The session's placement is missing")

        people: dict[SpeakerRole, str] = {}
        owners: dict[str, uuid.UUID] = {}
        for role, user in (
            (SpeakerRole.PS, row.ps),
            (SpeakerRole.SME, row.sme),
            (SpeakerRole.TECH_LEAD, row.tech_lead),
        ):
            if user is not None:
                people[role] = _person(user.full_name, user.email)
                owners[role.value] = user.id

        since = session.held_at - timedelta(
            days=settings.session_resolved_issue_lookback_days
        )
        issues = await self.signals.issues_to_offer(session.placement_id, since)
        actions = await self.signals.open_actions(session.placement_id)
        context = SessionContext(
            held_at=session.held_at,
            call_day=local_day(session.held_at, settings.recordings_timezone),
            consultant_name=row.consultant.full_name,
            client_name=row.client.name,
            project_name=row.project.name,
            client_manager_name=row.project.client_manager_name,
            people=people,
            utterances=list(transcript.utterances or []),
            full_text=transcript.full_text or "",
            earlier_issues=[
                IssueRef(
                    ref=f"I{n}",
                    issue_id=issue.id,
                    topic=issue.topic,
                    status=issue.status,
                    first_seen=local_day(
                        issue.first_seen_at, settings.recordings_timezone
                    ),
                    occurrence_count=issue.occurrence_count,
                )
                for n, issue in enumerate(issues, start=1)
            ],
            open_actions=[
                ActionRef(
                    ref=f"A{n}",
                    action_id=action.id,
                    description=action.description,
                    owner_role=action.owner_role,
                    due_text=action.due_text,
                )
                for n, action in enumerate(actions, start=1)
            ],
        )
        return _Loaded(context=context, owners=owners)

    async def _store(
        self,
        session: Session,
        job: ProcessingJob,
        loaded: _Loaded,
        result: SessionRunResult,
    ) -> None:
        for record in result.cost_records:
            self.db.add(
                ProcessingCost(
                    session_id=session.id, processing_job_id=job.id, **record
                )
            )
        session.node_errors = result.node_errors
        now = datetime.now(UTC)

        if not result.usable:
            session.status = SessionStatus.FAILED.value
            session.error_message = NOTHING_USABLE
            job.status = JobStatus.FAILED.value
            job.completed_at = now
            job.error_message = NOTHING_USABLE
            await self.db.commit()
            logger.warning("Session %s analysis produced nothing", session.id)
            return

        analysis = result.analysis
        await self.sessions.save_transcript(
            session.id,
            summary=analysis.summary,
            session_class=analysis.session_class,
            project_phase=analysis.project_phase,
            speaker_roles=analysis.speaker_roles,
        )
        if analysis.session_class and session.kind_overridden_by_user_id is None:
            session.kind = analysis.session_class

        held_at = session.held_at
        rows: list[Signal | Issue | Action] = []
        linked = await self.signals.issues_by_id(
            {d.earlier_issue_id for d in analysis.issues if d.earlier_issue_id}
        )
        counted: set[uuid.UUID] = set()
        for draft in analysis.issues:
            issue = (
                linked.get(draft.earlier_issue_id) if draft.earlier_issue_id else None
            )
            if issue is None:
                issue = Issue(
                    id=uuid.uuid4(),
                    placement_id=session.placement_id,
                    topic=draft.topic,
                    first_seen_at=held_at,
                    last_seen_at=held_at,
                    occurrence_count=1,
                    status=IssueStatus.OPEN.value,
                )
                rows.append(issue)
            else:
                if issue.id not in counted:
                    issue.occurrence_count += 1
                    counted.add(issue.id)
                issue.first_seen_at = min(issue.first_seen_at, held_at)
                latest = held_at >= issue.last_seen_at
                issue.last_seen_at = max(issue.last_seen_at, held_at)
                if (
                    not draft.resolved_by_end
                    and latest
                    and issue.status == IssueStatus.RESOLVED.value
                ):
                    issue.status = IssueStatus.OPEN.value
                    issue.resolved_at = None
            if draft.resolved_by_end and held_at >= issue.last_seen_at:
                issue.status = IssueStatus.RESOLVED.value
                issue.resolved_at = held_at
            rows.append(self._signal(session, draft.signal, issue.id))

        for signal in analysis.signals:
            rows.append(self._signal(session, signal, None))

        for action in analysis.actions:
            rows.append(
                Action(
                    placement_id=session.placement_id,
                    source_kind=SourceKind.SESSION.value,
                    source_id=session.id,
                    owner_role=action.owner_role,
                    owner_user_id=loaded.owners.get(action.owner_role),
                    description=action.description,
                    quote=action.quote,
                    offset_ms=action.offset_ms,
                    due_text=action.due_text,
                    due_date=action.due_date,
                )
            )

        closing = await self.signals.actions_by_id(analysis.closed_action_ids)
        for earlier in closing.values():
            if earlier.status != ActionStatus.DONE.value:
                earlier.status = ActionStatus.DONE.value
                earlier.closed_at = held_at
                earlier.closed_source_id = session.id

        await self.signals.add_all(rows)
        session.quotes_rejected = analysis.quotes_rejected
        session.status = SessionStatus.COMPLETED.value
        job.status = JobStatus.COMPLETED.value
        job.completed_at = now
        await self.db.commit()
        logger.info(
            "Session %s analysed: %d issue(s), %d other signal(s), %d action(s), "
            "%d closed, %d quote(s) rejected, %d node error(s)",
            session.id,
            len(analysis.issues),
            len(analysis.signals),
            len(analysis.actions),
            len(closing),
            analysis.quotes_rejected,
            len(result.node_errors),
        )

    @staticmethod
    def _signal(
        session: Session, draft: SignalDraft, issue_id: uuid.UUID | None
    ) -> Signal:
        offset = draft.offset_ms
        return Signal(
            placement_id=session.placement_id,
            source_kind=SourceKind.SESSION.value,
            source_id=session.id,
            category=draft.category,
            dimension=draft.dimension,
            polarity=draft.polarity,
            severity=draft.severity,
            confidence=draft.confidence,
            quote=draft.quote,
            note=draft.note,
            speaker_role=draft.speaker_role,
            occurred_at=session.held_at
            + timedelta(milliseconds=offset if offset is not None else 0),
            offset_ms=offset,
            issue_id=issue_id,
        )
