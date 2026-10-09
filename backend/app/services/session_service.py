"""Recorded sessions: created from a recording, an upload or a URL, then run.

Creating a session is quick and happens in the request: a scanned recording
or a URL only becomes a row, and an upload is stored as it arrives (it comes
with the request). The caller commits and then queues the session (``enqueue
_session``), because the worker opens its own database session and must see
the row.

The ``session`` job does the slow part, in order: copy the recording into
PMO's media bucket (server side) or download the URL, transcribe with
AssemblyAI and store the transcript and its cost, then analyse it with the
session pipeline (``session_analysis``). Status goes ``uploaded`` →
``transcribing`` (from the job's start) → ``transcribed`` → ``analyzing`` →
``completed``, or ``failed`` with the reason. A completed session's signals
are then embedded (``signal_embeddings``); that step never fails the session.
A job that finds its session already ``transcribed`` runs only the analysis.
A ``processing_jobs`` row
records each run: its stage (``copying``, ``downloading``, ``transcribing``,
``analyzing``), timing and error.

On takeover, sessions a stopped task left mid-run (``transcribing``,
``analyzing``) are failed, so a person can retry them, and sessions still
``uploaded`` or ``transcribed`` are queued again.
"""

import logging
import time
import uuid
from datetime import UTC, date, datetime

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.placement_repo import PlacementRepository
from app.db.repositories.recording_repo import RecordingRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.session import async_session_factory
from app.models.enums import (
    FolderMatchStatus,
    JobStatus,
    SessionKind,
    SessionSource,
    SessionStatus,
)
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.register import Placement
from app.models.session import Session
from app.services.cost_tracker import calculate_assemblyai_cost
from app.services.processing_ownership import (
    register_takeover_requeue,
    register_takeover_sweep,
)
from app.services.processing_queue import (
    SESSION_PRIORITY,
    Job,
    get_processing_queue,
    register_runner,
)
from app.services.recordings.folder_names import local_day
from app.services.session_analysis import Pipeline, SessionAnalysisService
from app.services.signal_embeddings import embed_session_signals
from app.services.storage import get_storage_backend
from app.services.storage.base import StorageBackend
from app.services.transcription.assemblyai_client import transcribe_media
from app.services.upload_service import UploadService, session_media_key
from app.services.url_download_service import UrlCheck, UrlDownloadService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

SESSION_JOB_KIND = "session"

# How long AssemblyAI may take to start reading the presigned recording URL.
MEDIA_URL_SECONDS = 2 * 60 * 60

# Mid-run statuses a stopped task leaves behind.
IN_FLIGHT = frozenset({SessionStatus.TRANSCRIBING.value, SessionStatus.ANALYZING.value})
# Statuses a job picks up: a new session, or one transcribed but not analysed.
WAITING = frozenset({SessionStatus.UPLOADED.value, SessionStatus.TRANSCRIBED.value})
INTERRUPTED_REASON = "Interrupted by a restart before it finished; retry it"

_registered = False


class PlacementChoiceError(ConflictError):
    """No single placement covers the call's date; a person must choose one."""

    def __init__(self, message: str, placement_ids: list[uuid.UUID]) -> None:
        super().__init__(message)
        self.placement_ids = placement_ids


def session_job(session_id: uuid.UUID) -> Job:
    return Job(kind=SESSION_JOB_KIND, id=session_id, priority=SESSION_PRIORITY)


def enqueue_session(session_id: uuid.UUID) -> bool:
    """Queue a committed session for its job."""
    return get_processing_queue().enqueue(session_job(session_id))


def call_date(held_at: datetime) -> date:
    """The calendar day of the call where it was held (``RECORDINGS_TIMEZONE``)."""
    return local_day(held_at, settings.recordings_timezone)


def covers(placement: Placement, day: date) -> bool:
    """Whether the placement's dates include ``day``, whatever its status:
    an ended placement still owns the calls held while it ran."""
    end = placement.expected_end_date
    return placement.start_date <= day and (end is None or day <= end)


def _in_utc(held_at: datetime) -> datetime:
    """The call time in UTC; a time without a zone is refused, not guessed."""
    if held_at.tzinfo is None:
        raise ValidationError("held_at must include a time zone")
    return held_at.astimezone(UTC)


class SessionService:
    """Creates sessions; used by the routes, inside the request's transaction."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        upload_service: UploadService | None = None,
        url_service: UrlDownloadService | None = None,
    ) -> None:
        self.db = db
        self.sessions = SessionRepository(db)
        self.recordings = RecordingRepository(db)
        self.placements = PlacementRepository(db)
        self._upload_service = upload_service
        self._url_service = url_service

    async def _placement(self, placement_id: uuid.UUID) -> Placement:
        placement = await self.placements.get_by_id(placement_id)
        if placement is None:
            raise NotFoundError("Placement", str(placement_id))
        return placement

    async def create_from_recording(
        self, recording_id: uuid.UUID, placement_id: uuid.UUID | None = None
    ) -> Session:
        """A session for a scanned recording, held at the file's time.

        The placement is the folder consultant's one whose dates cover the
        call; ``placement_id`` names it when none or several do, and must be
        one of that consultant's placements.
        """
        found = await self.recordings.get_recording(recording_id)
        if found is None:
            raise NotFoundError("Recording", str(recording_id))
        recording, folder = found
        if (
            folder.match_status
            not in (FolderMatchStatus.MATCHED.value, FolderMatchStatus.CHOSEN.value)
            or folder.consultant_id is None
        ):
            raise ConflictError("Choose the consultant for this folder first")
        existing = await self.sessions.get_for_recording(recording_id)
        if existing is not None:
            raise ConflictError(f"This recording is already session {existing.id}")

        held_at = recording.recorded_at or recording.last_modified
        options = await self.placements.list_for_consultant(folder.consultant_id)
        if placement_id is not None:
            if placement_id not in {p.id for p in options}:
                raise ValidationError(
                    "That placement is not one of this consultant's placements"
                )
            chosen = placement_id
        else:
            day = call_date(held_at)
            covering = [p for p in options if covers(p, day)]
            if len(covering) != 1:
                reason = (
                    "No placement of this consultant covers"
                    if not covering
                    else "More than one placement of this consultant covers"
                )
                choices = covering or options
                raise PlacementChoiceError(
                    f"{reason} {day.isoformat()}; choose the placement",
                    [p.id for p in choices],
                )
            chosen = covering[0].id

        session = Session(
            placement_id=chosen,
            held_at=held_at,
            source=SessionSource.S3.value,
            source_recording_id=recording.id,
            original_filename=recording.object_key.rsplit("/", 1)[-1],
        )
        try:
            async with self.db.begin_nested():
                await self.sessions.add(session)
        except IntegrityError as exc:
            # Another request processed the same recording a moment earlier.
            raise ConflictError("This recording is already being processed") from exc
        return session

    async def create_from_upload(
        self, file: UploadFile, placement_id: uuid.UUID, held_at: datetime
    ) -> Session:
        """A session for an uploaded recording, stored before this returns."""
        held_at = _in_utc(held_at)
        await self._placement(placement_id)
        upload = self._upload_service or UploadService()
        upload.validate_file(file)
        session = Session(
            placement_id=placement_id,
            held_at=held_at,
            source=SessionSource.UPLOAD.value,
            original_filename=file.filename,
        )
        await self.sessions.add(session)
        session.recording_key = await upload.store_file(file, session.id)
        await self.db.flush()
        return session

    async def create_from_url(
        self, url: str, placement_id: uuid.UUID, held_at: datetime
    ) -> Session:
        """A session for a recording at a URL, checked now, downloaded by the job."""
        held_at = _in_utc(held_at)
        await self._placement(placement_id)
        url_service = self._url_service or UrlDownloadService()
        check = await url_service.validate_url(url)
        session = Session(
            placement_id=placement_id,
            held_at=held_at,
            source=SessionSource.URL.value,
            source_url=url,
            original_filename=check.filename,
        )
        await self.sessions.add(session)
        return session

    async def retry(self, session: Session) -> Session:
        """Put a failed session back where it failed; the caller commits and queues.

        With a transcript it goes back to ``transcribed`` (analysis only);
        otherwise to ``uploaded``, and the job skips the copy or download when
        the recording is already stored. The failed job row and its costs stay.
        """
        if session.status != SessionStatus.FAILED.value:
            raise ConflictError("Only a failed session can be retried")
        transcript = await self.sessions.get_transcript(session.id)
        session.status = (
            SessionStatus.TRANSCRIBED.value
            if transcript is not None
            else SessionStatus.UPLOADED.value
        )
        session.error_message = None
        await self.db.flush()
        return session

    async def set_kind(
        self, session: Session, kind: SessionKind, user_id: uuid.UUID
    ) -> Session:
        """A person's kind for the call; later analysis keeps it."""
        session.kind = kind.value
        session.kind_overridden_by_user_id = user_id
        await self.db.flush()
        return session


class SessionRunner:
    """The ``session`` job: fetch the recording, transcribe, analyse, store."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        storage: StorageBackend | None = None,
        url_service: UrlDownloadService | None = None,
        pipeline: Pipeline | None = None,
    ) -> None:
        self.db = db
        self.sessions = SessionRepository(db)
        self.storage = storage or get_storage_backend()
        self._url_service = url_service
        self._pipeline = pipeline

    async def run(self, session_id: uuid.UUID) -> None:
        session = await self.sessions.get(session_id)
        if session is None:
            logger.warning("Session %s no longer exists; job skipped", session_id)
            return
        if session.status not in WAITING:
            logger.info(
                "Session %s is %s, not waiting; job skipped",
                session_id,
                session.status,
            )
            return
        analysis_only = session.status == SessionStatus.TRANSCRIBED.value

        job = ProcessingJob(
            kind=SESSION_JOB_KIND,
            subject_id=session_id,
            status=JobStatus.IN_PROGRESS.value,
            started_at=datetime.now(UTC),
        )
        await self.sessions.add(job)
        session.status = (
            SessionStatus.ANALYZING.value
            if analysis_only
            else SessionStatus.TRANSCRIBING.value
        )
        session.error_message = None
        await self.db.commit()
        job_id = job.id

        try:
            if not analysis_only:
                await self._fetch(session, job)
                await self._transcribe(session, job)
            await self._analyse(session, job)
        except Exception as exc:
            await self.db.rollback()
            reason = f"{type(exc).__name__}: {getattr(exc, 'message', None) or exc}"
            logger.exception("Session %s failed: %s", session_id, reason)
            failed = await self.sessions.get(session_id)
            failed_job = await self.db.get(ProcessingJob, job_id)
            if failed is not None:
                failed.status = SessionStatus.FAILED.value
                failed.error_message = reason[:2000]
            if failed_job is not None:
                failed_job.status = JobStatus.FAILED.value
                failed_job.completed_at = datetime.now(UTC)
                failed_job.error_message = reason[:2000]
            await self.db.commit()

    async def _stage(self, job: ProcessingJob, stage: str) -> None:
        job.stage = stage
        await self.db.commit()

    async def _fetch(self, session: Session, job: ProcessingJob) -> None:
        """Bring the recording into PMO's media bucket (an upload is there already)."""
        if session.recording_key:
            return
        filename = session.original_filename or "recording"
        if session.source == SessionSource.S3.value:
            recording = (
                await self.sessions.get_recording(session.source_recording_id)
                if session.source_recording_id
                else None
            )
            if recording is None:
                raise ValueError("The session's source recording is missing")
            await self._stage(job, "copying")
            key = await self.storage.copy_from_s3(
                settings.recordings_source_bucket,
                recording.object_key,
                session_media_key(session.id, filename),
            )
        elif session.source == SessionSource.URL.value and session.source_url:
            await self._stage(job, "downloading")
            url_service = self._url_service or UrlDownloadService(self.storage)
            key = await url_service.download_and_store(
                session.source_url, session.id, UrlCheck(filename, None, None)
            )
        else:
            raise ValueError(f"Session has no recording to fetch ({session.source})")
        session.recording_key = key
        await self.db.commit()

    async def _transcribe(self, session: Session, job: ProcessingJob) -> None:
        await self._stage(job, "transcribing")
        if not session.recording_key:
            raise ValueError("The session has no stored recording")
        media = await self.storage.get_url(
            session.recording_key, expires_in=MEDIA_URL_SECONDS
        )
        started = time.monotonic()
        transcription = await transcribe_media(media)
        elapsed = time.monotonic() - started

        await self.sessions.save_transcript(
            session.id,
            full_text=transcription.text,
            utterances=transcription.utterances,
        )
        audio_seconds = transcription.audio_duration_seconds
        session.duration_seconds = audio_seconds
        await self.sessions.add(
            ProcessingCost(
                session_id=session.id,
                processing_job_id=job.id,
                service="assemblyai",
                operation="transcription",
                amount_usd=calculate_assemblyai_cost(audio_seconds or 0.0),
                model=settings.assemblyai_speech_models[0],
                duration_seconds=elapsed,
                audio_duration_seconds=audio_seconds,
            )
        )
        session.status = SessionStatus.TRANSCRIBED.value
        await self.db.commit()
        logger.info(
            "Session %s transcribed (AssemblyAI %s, %.0f s of audio)",
            session.id,
            transcription.transcript_id,
            audio_seconds or 0.0,
        )

    async def _analyse(self, session: Session, job: ProcessingJob) -> None:
        session.status = SessionStatus.ANALYZING.value
        await self._stage(job, "analyzing")
        await SessionAnalysisService(self.db, pipeline=self._pipeline).analyse(
            session, job
        )
        if session.status == SessionStatus.COMPLETED.value:
            await embed_session_signals(self.db, session.id, job.id)


async def run_session_job(job: Job) -> None:
    async with async_session_factory() as db:
        await SessionRunner(db).run(job.id)


async def fail_interrupted_sessions() -> int:
    """Takeover sweep: sessions and session jobs left mid-run are failed."""
    async with async_session_factory() as db:
        repo = SessionRepository(db)
        failed = await repo.fail_with_status(IN_FLIGHT, INTERRUPTED_REASON)
        await repo.fail_running_jobs(
            SESSION_JOB_KIND, datetime.now(UTC), INTERRUPTED_REASON
        )
        await db.commit()
    return len(failed)


async def requeue_waiting_sessions() -> int:
    """Takeover re-queue: sessions not started, or transcribed but not yet
    analysed, go back on the queue."""
    async with async_session_factory() as db:
        waiting = await SessionRepository(db).ids_with_status(WAITING)
    return sum(1 for session_id in waiting if enqueue_session(session_id))


def register_session_processing() -> None:
    """Register the session runner, sweep and re-queue once; call before takeover."""
    global _registered
    if _registered:
        return
    register_runner(SESSION_JOB_KIND, run_session_job)
    register_takeover_sweep("sessions", fail_interrupted_sessions)
    register_takeover_requeue("sessions", requeue_waiting_sessions)
    _registered = True
