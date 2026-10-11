"""Queries for recorded sessions, their transcripts and their job records."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, SessionStatus, SourceKind
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session, SessionTranscript, SourceRecording
from app.models.signal import Action, Signal
from app.utils.entitlements import ListScope


@dataclass(frozen=True)
class SessionListRow:
    """A session with what the sessions list shows beside it, from one query."""

    session: Session
    consultant: Consultant
    project: Project
    client: Client
    signal_count: int
    action_count: int


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, session_id: uuid.UUID) -> Session | None:
        return await self.session.get(Session, session_id)

    async def get_for_recording(self, recording_id: uuid.UUID) -> Session | None:
        result = await self.session.execute(
            select(Session).where(Session.source_recording_id == recording_id)
        )
        return result.scalar_one_or_none()

    async def get_recording(self, recording_id: uuid.UUID) -> SourceRecording | None:
        return await self.session.get(SourceRecording, recording_id)

    async def add(self, row: Session | ProcessingCost | ProcessingJob) -> None:
        self.session.add(row)
        await self.session.flush()

    async def get_transcript(self, session_id: uuid.UUID) -> SessionTranscript | None:
        result = await self.session.execute(
            select(SessionTranscript).where(SessionTranscript.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def save_transcript(
        self, session_id: uuid.UUID, **fields: object
    ) -> SessionTranscript:
        """Create the session's transcript, or set fields on the existing one."""
        transcript = await self.get_transcript(session_id)
        if transcript is None:
            transcript = SessionTranscript(session_id=session_id)
            self.session.add(transcript)
        for name, value in fields.items():
            setattr(transcript, name, value)
        await self.session.flush()
        return transcript

    async def list_rows(
        self,
        scope: ListScope,
        *,
        consultant_id: uuid.UUID | None = None,
        placement_id: uuid.UUID | None = None,
        status: str | None = None,
        signal_dimension: str | None = None,
    ) -> list[SessionListRow]:
        """The sessions ``scope`` may see, newest call first, with their counts.

        ``signal_dimension`` counts only that dimension's signals (an SME's
        Technical view).
        """
        if scope.nothing:
            return []
        counted = select(Signal.source_id, func.count().label("n")).where(
            Signal.source_kind == SourceKind.SESSION.value
        )
        if signal_dimension is not None:
            counted = counted.where(Signal.dimension == signal_dimension)
        signal_counts = counted.group_by(Signal.source_id).subquery()
        action_counts = (
            select(Action.source_id, func.count().label("n"))
            .where(Action.source_kind == SourceKind.SESSION.value)
            .group_by(Action.source_id)
            .subquery()
        )
        stmt = (
            select(
                Session,
                Consultant,
                Project,
                Client,
                func.coalesce(signal_counts.c.n, 0),
                func.coalesce(action_counts.c.n, 0),
            )
            .join(Placement, Placement.id == Session.placement_id)
            .join(Consultant, Consultant.id == Placement.consultant_id)
            .join(Project, Project.id == Placement.project_id)
            .join(Client, Client.id == Project.client_id)
            .outerjoin(signal_counts, signal_counts.c.source_id == Session.id)
            .outerjoin(action_counts, action_counts.c.source_id == Session.id)
            .order_by(Session.held_at.desc(), Session.id)
        )
        if not scope.everything:
            user_id = scope.named_user_id
            stmt = stmt.where(
                or_(
                    Placement.ps_user_id == user_id,
                    Placement.sme_user_id == user_id,
                    Consultant.cdm_user_id == user_id,
                )
            )
        if consultant_id is not None:
            stmt = stmt.where(Placement.consultant_id == consultant_id)
        if placement_id is not None:
            stmt = stmt.where(Session.placement_id == placement_id)
        if status is not None:
            stmt = stmt.where(Session.status == status)
        result = await self.session.execute(stmt)
        return [SessionListRow(*row) for row in result.all()]

    async def last_completed_calls(
        self, placement_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """When each placement's latest completed call was held."""
        if not placement_ids:
            return {}
        result = await self.session.execute(
            select(Session.placement_id, func.max(Session.held_at))
            .where(
                Session.placement_id.in_(placement_ids),
                Session.status == SessionStatus.COMPLETED.value,
            )
            .group_by(Session.placement_id)
        )
        return {placement_id: held_at for placement_id, held_at in result.all()}

    async def costs_by_service(self, session_id: uuid.UUID) -> dict[str, float]:
        """The session's spend so far, in USD, per external service."""
        result = await self.session.execute(
            select(ProcessingCost.service, func.sum(ProcessingCost.amount_usd))
            .where(ProcessingCost.session_id == session_id)
            .group_by(ProcessingCost.service)
        )
        return {service: float(total) for service, total in result.all()}

    async def ids_with_status(self, statuses: Collection[str]) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(Session.id)
            .where(Session.status.in_(list(statuses)))
            .order_by(Session.created_at)
        )
        return list(result.scalars().all())

    async def fail_with_status(
        self, statuses: Collection[str], reason: str
    ) -> list[uuid.UUID]:
        """Mark every session in ``statuses`` failed; returns their ids."""
        result = await self.session.execute(
            update(Session)
            .where(Session.status.in_(list(statuses)))
            .values(status=SessionStatus.FAILED.value, error_message=reason)
            .returning(Session.id)
        )
        return list(result.scalars().all())

    async def fail_running_jobs(
        self, kind: str, finished_at: datetime, reason: str
    ) -> int:
        result = await self.session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.kind == kind,
                ProcessingJob.status == JobStatus.IN_PROGRESS.value,
            )
            .values(
                status=JobStatus.FAILED.value,
                completed_at=finished_at,
                error_message=reason,
            )
            .returning(ProcessingJob.id)
        )
        return len(result.all())
