"""Sessions from a recording, an upload or a URL, and the job that runs them.

Against a real database; storage, the URL service, AssemblyAI and the
analysis pipeline are fakes (the analysis itself is tested in
``test_session_analysis.py``).
"""

import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.ai.session.drafts import SessionAnalysis, SignalDraft
from app.ai.session.graph import SessionRunResult
from app.ai.session.state import SessionContext
from app.models.enums import FolderMatchStatus, JobStatus, SessionStatus, SnapshotReason
from app.models.processing_cost import ProcessingCost
from app.models.processing_job import ProcessingJob
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import (
    RecordingFolder,
    Session,
    SessionTranscript,
    SourceRecording,
)
from app.models.signal import Signal
from app.services import session_analysis, session_service, signal_embeddings
from app.services.health_jobs import RECOMPUTE_JOB_KIND, recompute_job
from app.services.processing_queue import get_processing_queue
from app.services.session_service import (
    PlacementChoiceError,
    SessionRunner,
    SessionService,
    fail_interrupted_sessions,
    requeue_waiting_sessions,
    session_job,
)
from app.services.signal_embeddings import EMBEDDING_OPERATION
from app.services.storage.local import LocalStorageBackend
from app.services.transcription.assemblyai_client import Transcription
from app.services.upload_service import UploadService
from app.services.url_download_service import UrlCheck
from app.utils.exceptions import (
    ConflictError,
    NotFoundError,
    TranscriptionError,
    ValidationError,
)
from tests.unit.embedding_helpers import FakeEmbeddingClient

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
# 23:30 UTC on 30 September is 00:30 on 1 October in London (BST).
LATE_CALL = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)


class World:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def consultant(self, name: str = "Priya Shah") -> Consultant:
        consultant = Consultant(full_name=name)
        client = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
        self.db.add_all([consultant, client])
        await self.db.flush()
        self.project = Project(client_id=client.id, name="Data platform")
        self.db.add(self.project)
        await self.db.flush()
        return consultant

    async def placement(
        self, consultant: Consultant, start: date, end: date | None
    ) -> Placement:
        placement = Placement(
            consultant_id=consultant.id,
            project_id=self.project.id,
            start_date=start,
            expected_end_date=end,
        )
        self.db.add(placement)
        await self.db.flush()
        return placement

    async def recording(
        self,
        consultant: Consultant | None,
        *,
        recorded_at: datetime | None = LATE_CALL,
        status: FolderMatchStatus = FolderMatchStatus.MATCHED,
    ) -> SourceRecording:
        folder = RecordingFolder(
            folder_key=f"recordings/pmo/{uuid.uuid4()}/",
            display_name="PMO support Priya",
            consultant_id=consultant.id if consultant else None,
            match_status=status.value,
            last_seen_at=LATE_CALL,
        )
        self.db.add(folder)
        await self.db.flush()
        recording = SourceRecording(
            folder_id=folder.id,
            object_key=f"{folder.folder_key}Recording 2026-10-01 00-30-00.webm",
            size_bytes=131_000_000,
            last_modified=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
            recorded_at=recorded_at,
        )
        self.db.add(recording)
        await self.db.flush()
        return recording


class FakeStorage(LocalStorageBackend):
    def __init__(self, base_dir: str) -> None:
        super().__init__(base_dir)
        self.copies: list[tuple[str, str, str]] = []

    async def copy_from_s3(
        self, source_bucket: str, source_key: str, file_key: str
    ) -> str:
        self.copies.append((source_bucket, source_key, file_key))
        await self.upload(file_key, WEBM)
        return file_key


class FakeUrlService:
    def __init__(self) -> None:
        self.downloads: list[str] = []

    async def validate_url(self, url: str) -> UrlCheck:
        return UrlCheck("call.webm", "video/webm", 1000)

    async def download_and_store(
        self, url: str, session_id: uuid.UUID, check: UrlCheck
    ) -> str:
        self.downloads.append(url)
        return f"sessions/{session_id}/{check.filename}"


@pytest.fixture
def world(db_session: AsyncSession) -> World:
    return World(db_session)


@pytest.fixture(autouse=True)
def analysed(monkeypatch: pytest.MonkeyPatch) -> list[SessionContext]:
    """The session pipeline answering with a summary; records what it was given."""
    given: list[SessionContext] = []

    async def fake(context: SessionContext) -> SessionRunResult:
        given.append(context)
        return SessionRunResult(
            analysis=SessionAnalysis(summary="A short call."),
            cost_records=[],
            node_errors=[],
            succeeded=["summarise"],
        )

    monkeypatch.setattr(session_analysis, "run_session_pipeline", fake)
    return given


@pytest.fixture
def transcribed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """AssemblyAI answering with a two-line transcript; records what it was sent."""
    sent: list[str] = []

    async def fake(media: str) -> Transcription:
        sent.append(media)
        return Transcription(
            transcript_id="t-9",
            text="Morning. Morning.",
            utterances=[
                {
                    "speaker": "A",
                    "text": "Morning.",
                    "start_ms": 0,
                    "end_ms": 800,
                    "confidence": 0.9,
                },
                {
                    "speaker": "B",
                    "text": "Morning.",
                    "start_ms": 900,
                    "end_ms": 1600,
                    "confidence": 0.9,
                },
            ],
            audio_duration_seconds=1800.0,
        )

    monkeypatch.setattr(session_service, "transcribe_media", fake)
    return sent


class TestCreateFromRecording:
    async def test_the_placement_covering_the_uk_call_date_is_used(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        await world.placement(priya, date(2026, 3, 1), date(2026, 9, 30))
        october = await world.placement(priya, date(2026, 10, 1), None)
        recording = await world.recording(priya)

        session = await SessionService(db_session).create_from_recording(recording.id)

        assert session.placement_id == october.id
        assert session.held_at == LATE_CALL
        assert session.source == "s3"
        assert session.status == SessionStatus.UPLOADED.value
        assert session.kind is None
        assert session.original_filename == "Recording 2026-10-01 00-30-00.webm"

    async def test_an_ended_placement_still_owns_its_old_calls(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        ended = await world.placement(priya, date(2026, 1, 1), date(2026, 12, 31))
        ended.status = "ended"
        recording = await world.recording(priya)

        session = await SessionService(db_session).create_from_recording(recording.id)
        assert session.placement_id == ended.id

    async def test_no_covering_placement_asks_for_any_of_the_consultant_s(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        early = await world.placement(priya, date(2025, 1, 1), date(2025, 6, 30))
        recording = await world.recording(priya)

        with pytest.raises(PlacementChoiceError, match="No placement") as caught:
            await SessionService(db_session).create_from_recording(recording.id)
        assert caught.value.placement_ids == [early.id]
        assert caught.value.status_code == 409

    async def test_two_covering_placements_ask_for_one_of_them(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        a = await world.placement(priya, date(2026, 9, 1), None)
        b = await world.placement(priya, date(2026, 9, 15), date(2026, 12, 31))
        await world.placement(priya, date(2025, 1, 1), date(2025, 6, 30))
        recording = await world.recording(priya)

        with pytest.raises(PlacementChoiceError, match="More than one") as caught:
            await SessionService(db_session).create_from_recording(recording.id)
        assert set(caught.value.placement_ids) == {a.id, b.id}

    async def test_chosen_placement_is_used_when_it_is_the_consultant_s(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        early = await world.placement(priya, date(2025, 1, 1), date(2025, 6, 30))
        recording = await world.recording(priya)

        session = await SessionService(db_session).create_from_recording(
            recording.id, early.id
        )
        assert session.placement_id == early.id

    async def test_another_consultant_s_placement_is_refused(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        ravi = await world.consultant("Ravi Kumar")
        theirs = await world.placement(ravi, date(2026, 1, 1), None)
        recording = await world.recording(priya)

        with pytest.raises(ValidationError, match="not one of this consultant"):
            await SessionService(db_session).create_from_recording(
                recording.id, theirs.id
            )

    async def test_folder_without_a_decided_consultant_is_refused(
        self, db_session: AsyncSession, world: World
    ) -> None:
        await world.consultant()
        recording = await world.recording(None, status=FolderMatchStatus.NEEDS_CHOICE)

        with pytest.raises(ConflictError, match="Choose the consultant"):
            await SessionService(db_session).create_from_recording(recording.id)

    async def test_a_recording_is_processed_once(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        await world.placement(priya, date(2026, 1, 1), None)
        recording = await world.recording(priya)
        service = SessionService(db_session)
        first = await service.create_from_recording(recording.id)

        with pytest.raises(ConflictError, match=str(first.id)):
            await service.create_from_recording(recording.id)

    async def test_file_without_a_time_is_held_at_its_s3_time(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        await world.placement(priya, date(2026, 1, 1), None)
        recording = await world.recording(priya, recorded_at=None)

        session = await SessionService(db_session).create_from_recording(recording.id)
        assert session.held_at == recording.last_modified

    async def test_unknown_recording_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(NotFoundError):
            await SessionService(db_session).create_from_recording(uuid.uuid4())


class TestCreateFromUploadAndUrl:
    async def test_upload_is_stored_under_the_new_session(
        self, db_session: AsyncSession, world: World, tmp_path: Path
    ) -> None:
        priya = await world.consultant()
        placement = await world.placement(priya, date(2026, 1, 1), None)
        upload = UploadService(storage=LocalStorageBackend(str(tmp_path)))
        file = UploadFile(
            file=io.BytesIO(WEBM),
            filename="check-in.webm",
            size=len(WEBM),
            headers=Headers({}),
        )

        session = await SessionService(
            db_session, upload_service=upload
        ).create_from_upload(file, placement.id, LATE_CALL)

        assert session.source == "upload"
        assert session.recording_key == f"sessions/{session.id}/check-in.webm"
        assert (tmp_path / session.recording_key).read_bytes() == WEBM

    async def test_url_is_checked_now_and_left_for_the_job(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        placement = await world.placement(priya, date(2026, 1, 1), None)
        urls = FakeUrlService()

        session = await SessionService(
            db_session,
            url_service=urls,  # type: ignore[arg-type]
        ).create_from_url("https://media.example.com/c.webm", placement.id, LATE_CALL)

        assert session.source == "url"
        assert session.source_url == "https://media.example.com/c.webm"
        assert session.original_filename == "call.webm"
        assert session.recording_key is None
        assert urls.downloads == []

    async def test_held_at_without_a_zone_is_refused(
        self, db_session: AsyncSession, world: World
    ) -> None:
        priya = await world.consultant()
        placement = await world.placement(priya, date(2026, 1, 1), None)

        with pytest.raises(ValidationError, match="time zone"):
            await SessionService(
                db_session,
                url_service=FakeUrlService(),  # type: ignore[arg-type]
            ).create_from_url(
                "https://media.example.com/c.webm",
                placement.id,
                datetime(2026, 10, 1, 9, 0),
            )

    async def test_unknown_placement_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(NotFoundError):
            await SessionService(
                db_session,
                url_service=FakeUrlService(),  # type: ignore[arg-type]
            ).create_from_url("https://m.example/c.webm", uuid.uuid4(), LATE_CALL)


async def _session(db: AsyncSession, world: World, **fields: Any) -> Session:
    priya = await world.consultant()
    placement = await world.placement(priya, date(2026, 1, 1), None)
    session = Session(placement_id=placement.id, held_at=LATE_CALL, **fields)
    db.add(session)
    await db.flush()
    return session


async def _job(db: AsyncSession, session_id: uuid.UUID) -> ProcessingJob:
    job = await db.scalar(
        select(ProcessingJob).where(ProcessingJob.subject_id == session_id)
    )
    assert job is not None
    await db.refresh(job)
    return job


class TestSessionRunner:
    async def test_recording_is_copied_transcribed_costed_then_analysed(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        transcribed: list[str],
        analysed: list[SessionContext],
    ) -> None:
        priya = await world.consultant()
        await world.placement(priya, date(2026, 1, 1), None)
        recording = await world.recording(priya)
        session = await SessionService(db_session).create_from_recording(recording.id)
        storage = FakeStorage(str(tmp_path))

        await SessionRunner(db_session, storage=storage).run(session.id)

        await db_session.refresh(session)
        key = f"sessions/{session.id}/Recording_2026-10-01_00-30-00.webm"
        assert storage.copies == [
            ("nextcloud-talk-recordings-itc", recording.object_key, key)
        ]
        assert session.recording_key == key
        assert transcribed == [str(tmp_path / key)]
        assert session.status == SessionStatus.COMPLETED.value
        assert session.duration_seconds == 1800.0

        transcript = await db_session.scalar(
            select(SessionTranscript).where(SessionTranscript.session_id == session.id)
        )
        assert transcript is not None
        await db_session.refresh(transcript)
        assert transcript.full_text == "Morning. Morning."
        assert len(transcript.utterances or []) == 2
        assert transcript.summary == "A short call."
        [context] = analysed
        assert context.full_text == "Morning. Morning."

        cost = await db_session.scalar(
            select(ProcessingCost).where(ProcessingCost.session_id == session.id)
        )
        assert cost is not None
        assert cost.service == "assemblyai"
        assert cost.amount_usd == pytest.approx(0.115)  # 0.5 h at $0.23/h
        assert cost.audio_duration_seconds == 1800.0

        job = await _job(db_session, session.id)
        assert job.status == JobStatus.COMPLETED.value
        assert job.stage == "analyzing"
        assert cost.processing_job_id == job.id

    async def test_url_session_is_downloaded_by_the_job(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        transcribed: list[str],
    ) -> None:
        session = await _session(
            db_session,
            world,
            source="url",
            source_url="https://media.example.com/c.webm",
            original_filename="c.webm",
        )
        urls = FakeUrlService()

        await SessionRunner(
            db_session,
            storage=FakeStorage(str(tmp_path)),
            url_service=urls,  # type: ignore[arg-type]
        ).run(session.id)

        await db_session.refresh(session)
        assert urls.downloads == ["https://media.example.com/c.webm"]
        assert session.recording_key == f"sessions/{session.id}/c.webm"
        assert session.status == SessionStatus.COMPLETED.value

    async def test_upload_is_transcribed_without_fetching(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        transcribed: list[str],
    ) -> None:
        session = await _session(
            db_session, world, source="upload", recording_key="sessions/x/a.webm"
        )
        storage = FakeStorage(str(tmp_path))

        await SessionRunner(db_session, storage=storage).run(session.id)

        await db_session.refresh(session)
        assert storage.copies == []
        assert session.status == SessionStatus.COMPLETED.value

    async def test_transcription_failure_fails_the_session_and_its_job(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def failing(media: str) -> Transcription:
            raise TranscriptionError("AssemblyAI failed transcript t-1: no audio")

        monkeypatch.setattr(session_service, "transcribe_media", failing)
        session = await _session(
            db_session, world, source="upload", recording_key="sessions/x/a.webm"
        )

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session.id
        )

        await db_session.refresh(session)
        assert session.status == SessionStatus.FAILED.value
        assert session.error_message == (
            "TranscriptionError: AssemblyAI failed transcript t-1: no audio"
        )
        job = await _job(db_session, session.id)
        assert job.status == JobStatus.FAILED.value
        assert job.stage == "transcribing"
        assert job.completed_at is not None

    async def test_transcribed_session_is_only_analysed(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        analysed: list[SessionContext],
    ) -> None:
        async def never(media: str) -> Transcription:
            raise AssertionError("a transcribed session is not transcribed again")

        monkeypatch.setattr(session_service, "transcribe_media", never)
        session = await _session(
            db_session,
            world,
            source="upload",
            recording_key="sessions/x/a.webm",
            status="transcribed",
        )
        db_session.add(
            SessionTranscript(session_id=session.id, full_text="Hello.", utterances=[])
        )
        await db_session.flush()
        storage = FakeStorage(str(tmp_path))

        await SessionRunner(db_session, storage=storage).run(session.id)

        await db_session.refresh(session)
        assert session.status == SessionStatus.COMPLETED.value
        assert storage.copies == []
        assert [c.full_text for c in analysed] == ["Hello."]
        job = await _job(db_session, session.id)
        assert job.status == JobStatus.COMPLETED.value
        assert job.stage == "analyzing"

    async def test_analysis_failure_fails_the_session_and_its_job(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        transcribed: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def broken(context: SessionContext) -> SessionRunResult:
            raise RuntimeError("graph bug")

        monkeypatch.setattr(session_analysis, "run_session_pipeline", broken)
        session = await _session(
            db_session, world, source="upload", recording_key="sessions/x/a.webm"
        )

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session.id
        )

        await db_session.refresh(session)
        assert session.status == SessionStatus.FAILED.value
        assert session.error_message == "RuntimeError: graph bug"
        job = await _job(db_session, session.id)
        assert job.status == JobStatus.FAILED.value
        assert job.stage == "analyzing"

    async def _transcribed(self, db: AsyncSession, world: World) -> Session:
        session = await _session(
            db,
            world,
            source="upload",
            recording_key="sessions/x/a.webm",
            status="transcribed",
        )
        db.add(
            SessionTranscript(session_id=session.id, full_text="Hello.", utterances=[])
        )
        await db.flush()
        return session

    @staticmethod
    def _with_a_signal(monkeypatch: pytest.MonkeyPatch, *, usable: bool) -> None:
        async def fake(context: SessionContext) -> SessionRunResult:
            draft = SignalDraft(
                category="client",
                dimension="delivery",
                polarity="negative",
                severity=2,
                confidence=0.8,
                quote="Hello.",
                note=None,
                speaker_role=None,
                offset_ms=0,
            )
            return SessionRunResult(
                analysis=SessionAnalysis(summary="A short call.", signals=[draft]),
                cost_records=[],
                node_errors=[],
                succeeded=["summarise"] if usable else [],
            )

        monkeypatch.setattr(session_analysis, "run_session_pipeline", fake)

    async def test_a_completed_analysis_embeds_its_signals(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._with_a_signal(monkeypatch, usable=True)
        client = FakeEmbeddingClient()
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)
        session = await self._transcribed(db_session, world)

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session.id
        )

        await db_session.refresh(session)
        assert session.status == SessionStatus.COMPLETED.value
        assert [r["input"] for r in client.embeddings.requests] == [["Hello."]]
        signal = await db_session.scalar(
            select(Signal).where(Signal.source_id == session.id)
        )
        assert signal is not None
        assert signal.embedding is not None
        job = await _job(db_session, session.id)
        operations = await db_session.scalars(
            select(ProcessingCost.operation).where(
                ProcessingCost.processing_job_id == job.id
            )
        )
        assert list(operations) == [EMBEDDING_OPERATION]
        # Then the placement's health is recomputed
        assert get_processing_queue().is_queued(
            recompute_job(session.placement_id, SnapshotReason.CALL)
        )

    async def test_an_embedding_failure_leaves_the_session_completed(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._with_a_signal(monkeypatch, usable=True)
        client = FakeEmbeddingClient(error=RuntimeError("Azure unavailable"))
        monkeypatch.setattr(signal_embeddings, "build_embedding_client", lambda: client)
        session = await self._transcribed(db_session, world)
        session_id = session.id
        placement_id = session.placement_id

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session_id
        )

        stored = await db_session.get(Session, session_id, populate_existing=True)
        assert stored is not None
        assert stored.status == SessionStatus.COMPLETED.value
        assert stored.error_message is None
        job = await _job(db_session, session_id)
        assert job.status == JobStatus.COMPLETED.value
        signal = await db_session.scalar(
            select(Signal).where(Signal.source_id == session_id)
        )
        assert signal is not None
        assert signal.embedding is None
        # The health recompute is queued all the same
        [recompute] = [
            j for j in get_processing_queue().snapshot().pending if j.id == placement_id
        ]
        assert recompute == recompute_job(placement_id, SnapshotReason.CALL)

    async def test_an_analysis_that_produced_nothing_is_not_embedded(
        self,
        db_session: AsyncSession,
        world: World,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._with_a_signal(monkeypatch, usable=False)
        embedded: list[uuid.UUID] = []

        async def record(db: AsyncSession, session_id: uuid.UUID, *args: Any) -> None:
            embedded.append(session_id)

        monkeypatch.setattr(session_service, "embed_session_signals", record)
        session = await self._transcribed(db_session, world)

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session.id
        )

        await db_session.refresh(session)
        assert session.status == SessionStatus.FAILED.value
        assert embedded == []
        assert [
            j
            for j in get_processing_queue().snapshot().pending
            if j.kind == RECOMPUTE_JOB_KIND
        ] == []

    async def test_session_not_waiting_is_left_alone(
        self, db_session: AsyncSession, world: World, tmp_path: Path
    ) -> None:
        session = await _session(db_session, world, source="upload", status="completed")

        await SessionRunner(db_session, storage=FakeStorage(str(tmp_path))).run(
            session.id
        )

        assert (
            await db_session.scalar(
                select(ProcessingJob).where(ProcessingJob.subject_id == session.id)
            )
            is None
        )


class TestTakeover:
    @pytest.fixture(autouse=True)
    def _use_test_session(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @asynccontextmanager
        async def factory() -> AsyncIterator[AsyncSession]:
            yield db_session

        monkeypatch.setattr(session_service, "async_session_factory", factory)

    async def test_sessions_left_mid_run_are_failed(
        self, db_session: AsyncSession, world: World
    ) -> None:
        mid = await _session(db_session, world, source="upload", status="transcribing")
        waiting = await _session(db_session, world, source="upload")
        running_job = ProcessingJob(
            kind="session", subject_id=mid.id, status=JobStatus.IN_PROGRESS.value
        )
        db_session.add(running_job)
        await db_session.flush()

        assert await fail_interrupted_sessions() == 1

        await db_session.refresh(mid)
        await db_session.refresh(waiting)
        await db_session.refresh(running_job)
        assert mid.status == SessionStatus.FAILED.value
        assert "retry" in (mid.error_message or "")
        assert waiting.status == SessionStatus.UPLOADED.value
        assert running_job.status == JobStatus.FAILED.value

    async def test_waiting_and_transcribed_sessions_are_queued_again(
        self, db_session: AsyncSession, world: World
    ) -> None:
        waiting = await _session(db_session, world, source="upload")
        transcribed = await _session(
            db_session, world, source="upload", status="transcribed"
        )
        done = await _session(db_session, world, source="upload", status="completed")

        assert await requeue_waiting_sessions() == 2
        queue = get_processing_queue()
        assert queue.is_queued(session_job(waiting.id))
        assert queue.is_queued(session_job(transcribed.id))
        assert not queue.is_queued(session_job(done.id))
