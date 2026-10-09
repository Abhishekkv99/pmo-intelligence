"""Queries for recorded sessions, their transcripts and their job records."""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, SessionStatus
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.session import Session, SessionTranscript, SourceRecording


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
