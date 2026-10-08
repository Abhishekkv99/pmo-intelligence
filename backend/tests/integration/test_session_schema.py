"""The session and recordings tables' constraints against a real database.

Pins what the scanner and the session service will rely on: one session per
recording, enumerated columns limited to their sets (a session's kind may be
empty until the pipeline classifies it), and a session's cost rows outliving
the session.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FolderMatchStatus, SessionSource, SessionStatus
from app.models.processing_cost import ProcessingCost
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import (
    RecordingFolder,
    Session,
    SessionTranscript,
    SourceRecording,
)

NOW = datetime(2026, 10, 8, 10, 30, tzinfo=UTC)


async def _placement(db: AsyncSession) -> Placement:
    client = Client(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    consultant = Consultant(full_name="Priya Shah")
    db.add_all([client, consultant])
    await db.flush()
    project = Project(client_id=client.id, name="Data platform")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id, project_id=project.id, start_date=date(2026, 9, 1)
    )
    db.add(placement)
    await db.flush()
    return placement


async def _recording(db: AsyncSession) -> SourceRecording:
    folder = RecordingFolder(
        folder_key=f"recordings/pmo/{uuid.uuid4()}/",
        display_name="01-10-26 - PMO support Priya",
        last_seen_at=NOW,
    )
    db.add(folder)
    await db.flush()
    recording = SourceRecording(
        folder_id=folder.id,
        object_key=f"{folder.folder_key}Recording 2026-10-01 10-00-00.webm",
        size_bytes=131_000_000,
        last_modified=NOW,
    )
    db.add(recording)
    await db.flush()
    return recording


def _session(placement: Placement, **fields: object) -> Session:
    return Session(
        placement_id=placement.id,
        held_at=NOW,
        source=SessionSource.S3.value,
        **fields,
    )


class TestSessionDefaults:
    async def test_new_session_is_uploaded_unclassified_with_no_errors(
        self, db_session: AsyncSession
    ) -> None:
        session = _session(await _placement(db_session))
        db_session.add(session)
        await db_session.flush()
        await db_session.refresh(session)

        assert session.status == SessionStatus.UPLOADED.value
        assert session.kind is None
        assert session.quotes_rejected == 0
        assert session.node_errors == []

    async def test_new_folder_is_unmatched_with_no_candidates(
        self, db_session: AsyncSession
    ) -> None:
        folder = RecordingFolder(
            folder_key="recordings/pmo/x/", display_name="x", last_seen_at=NOW
        )
        db_session.add(folder)
        await db_session.flush()
        await db_session.refresh(folder)

        assert folder.match_status == FolderMatchStatus.UNMATCHED.value
        assert folder.candidate_consultant_ids == []


class TestSessionConstraints:
    async def test_second_session_for_one_recording_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        recording = await _recording(db_session)
        db_session.add(_session(placement, source_recording_id=recording.id))
        await db_session.flush()

        db_session.add(_session(placement, source_recording_id=recording.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("kind", "standup"),
            ("source", "dropbox"),
            ("status", "queued"),
        ],
    )
    async def test_session_value_outside_its_set_is_refused(
        self, db_session: AsyncSession, field: str, value: str
    ) -> None:
        placement = await _placement(db_session)
        session = _session(placement)
        setattr(session, field, value)
        db_session.add(session)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_folder_match_status_outside_its_set_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(
            RecordingFolder(
                folder_key="recordings/pmo/y/",
                display_name="y",
                last_seen_at=NOW,
                match_status="guessed",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_second_transcript_for_one_session_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        session = _session(await _placement(db_session))
        db_session.add(session)
        await db_session.flush()
        db_session.add(SessionTranscript(session_id=session.id, full_text="a"))
        await db_session.flush()

        db_session.add(SessionTranscript(session_id=session.id, full_text="b"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_cost_rows_outlive_their_session(
        self, db_session: AsyncSession
    ) -> None:
        session = _session(await _placement(db_session))
        db_session.add(session)
        await db_session.flush()
        cost = ProcessingCost(
            session_id=session.id,
            service="assemblyai",
            operation="transcribe",
            amount_usd=0.12,
        )
        db_session.add(cost)
        await db_session.flush()

        await db_session.delete(session)
        await db_session.flush()

        kept = await db_session.execute(
            select(ProcessingCost.session_id).where(ProcessingCost.id == cost.id)
        )
        assert kept.one() == (None,)

    async def test_cost_for_an_unknown_session_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(
            ProcessingCost(
                session_id=uuid.uuid4(),
                service="assemblyai",
                operation="transcribe",
                amount_usd=0.12,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
