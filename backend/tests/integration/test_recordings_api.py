"""Admin > Recordings and the session upload and URL routes, against Postgres."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import FolderMatchStatus, ScanStatus
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import (
    RecordingFolder,
    RecordingScan,
    Session,
    SourceRecording,
)
from app.services.processing_queue import get_processing_queue
from app.services.recordings.periodic import scan_job
from app.services.session_service import session_job
from app.services.url_download_service import UrlCheck, UrlDownloadService

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
CALL = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


class Seed:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def consultant(self, name: str) -> Consultant:
        consultant = Consultant(full_name=name)
        self.db.add(consultant)
        await self.db.flush()
        return consultant

    async def placement(
        self, consultant: Consultant, start: date, end: date | None = None
    ) -> Placement:
        client = Client(name="Northwind", normalized_name=f"northwind {uuid.uuid4()}")
        self.db.add(client)
        await self.db.flush()
        project = Project(client_id=client.id, name="Data platform")
        self.db.add(project)
        await self.db.flush()
        placement = Placement(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=start,
            expected_end_date=end,
        )
        self.db.add(placement)
        await self.db.flush()
        return placement

    async def folder(
        self,
        name: str,
        status: FolderMatchStatus,
        consultant: Consultant | None = None,
        candidates: list[Consultant] | None = None,
        folder_date: date | None = None,
    ) -> RecordingFolder:
        folder = RecordingFolder(
            folder_key=f"recordings/pmo/{name}/",
            display_name=name,
            folder_date=folder_date,
            consultant_id=consultant.id if consultant else None,
            match_status=status.value,
            candidate_consultant_ids=[str(c.id) for c in candidates or []],
            last_seen_at=CALL,
        )
        self.db.add(folder)
        await self.db.flush()
        return folder

    async def recording(
        self, folder: RecordingFolder, name: str, recorded_at: datetime | None = CALL
    ) -> SourceRecording:
        recording = SourceRecording(
            folder_id=folder.id,
            object_key=f"{folder.folder_key}{name}",
            size_bytes=131_000_000,
            last_modified=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            recorded_at=recorded_at,
        )
        self.db.add(recording)
        await self.db.flush()
        return recording


@pytest.fixture
def seed(db_session: AsyncSession) -> Seed:
    return Seed(db_session)


class TestFolderList:
    async def test_lists_decided_and_undecided_folders_with_recordings(
        self, manager_client: AsyncClient, seed: Seed, db_session: AsyncSession
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        priya = await seed.consultant("Priya Shah")
        priya2 = await seed.consultant("Priya Patel")
        matched = await seed.folder(
            "14-09-26 - PMO support Ann",
            FolderMatchStatus.MATCHED,
            ann,
            folder_date=date(2026, 9, 14),
        )
        await seed.folder(
            "Priya check-in", FolderMatchStatus.NEEDS_CHOICE, candidates=[priya, priya2]
        )
        await seed.folder("team call", FolderMatchStatus.UNMATCHED)
        timed = await seed.recording(matched, "Recording 2026-10-01 10-00-00.webm")
        await seed.recording(matched, "Mani 2.webm", recorded_at=None)
        placement = await seed.placement(ann, date(2026, 1, 1))
        processed = Session(
            placement_id=placement.id,
            held_at=CALL,
            source="s3",
            source_recording_id=timed.id,
        )
        db_session.add(processed)
        db_session.add(
            RecordingScan(
                started_at=CALL, finished_at=CALL, status=ScanStatus.COMPLETED.value
            )
        )
        await db_session.flush()

        response = await manager_client.get("/api/v1/recording-folders")

        assert response.status_code == 200
        body = response.json()
        assert [f["display_name"] for f in body["folders"]] == [
            "14-09-26 - PMO support Ann",
            "Priya check-in",
        ]
        first, second = body["folders"]
        assert first["consultant"] == {"id": str(ann.id), "full_name": "Ann Brooks"}
        assert [r["filename"] for r in first["recordings"]] == [
            "Mani 2.webm",
            "Recording 2026-10-01 10-00-00.webm",
        ]
        untimed, timed_item = first["recordings"]
        assert untimed["time_from_name"] is False
        assert untimed["recorded_at"].startswith("2026-10-01T10:00:00")
        assert untimed["session"] is None
        assert timed_item["session"] == {"id": str(processed.id), "status": "uploaded"}
        assert second["match_status"] == "needs_choice"
        assert {c["full_name"] for c in second["candidates"]} == {
            "Priya Shah",
            "Priya Patel",
        }
        assert body["latest_scan"]["status"] == "completed"
        assert body["scan_enabled"] is settings.recordings_scan_enabled
        assert body["scan_interval_seconds"] == 900

    async def test_scoped_roles_cannot_see_the_folder(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.get("/api/v1/recording-folders")
        assert response.status_code == 403


class TestChooseConsultant:
    async def test_choice_ties_the_folder_and_clears_the_candidates(
        self, manager_client: AsyncClient, seed: Seed, db_session: AsyncSession
    ) -> None:
        priya = await seed.consultant("Priya Shah")
        other = await seed.consultant("Priya Patel")
        folder = await seed.folder(
            "Priya check-in", FolderMatchStatus.NEEDS_CHOICE, candidates=[priya, other]
        )

        response = await manager_client.put(
            f"/api/v1/recording-folders/{folder.id}/consultant",
            json={"consultant_id": str(priya.id)},
        )

        assert response.status_code == 204
        await db_session.refresh(folder)
        assert folder.match_status == FolderMatchStatus.CHOSEN.value
        assert folder.consultant_id == priya.id
        assert folder.candidate_consultant_ids == []

    async def test_unknown_consultant_is_refused(
        self, manager_client: AsyncClient, seed: Seed
    ) -> None:
        folder = await seed.folder("x", FolderMatchStatus.NEEDS_CHOICE)
        response = await manager_client.put(
            f"/api/v1/recording-folders/{folder.id}/consultant",
            json={"consultant_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422

    async def test_unknown_folder_is_not_found(
        self, manager_client: AsyncClient, seed: Seed
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        response = await manager_client.put(
            f"/api/v1/recording-folders/{uuid.uuid4()}/consultant",
            json={"consultant_id": str(ann.id)},
        )
        assert response.status_code == 404


class TestScan:
    async def test_scan_now_queues_one_scan(self, manager_client: AsyncClient) -> None:
        first = await manager_client.post("/api/v1/recordings/scan")
        second = await manager_client.post("/api/v1/recordings/scan")

        assert first.status_code == 202
        assert first.json() == {"queued": True}
        assert second.json() == {"queued": False}
        assert get_processing_queue().is_queued(scan_job())

    async def test_scoped_roles_cannot_scan(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post("/api/v1/recordings/scan")
        assert response.status_code == 403
        assert not get_processing_queue().is_queued(scan_job())


class TestProcess:
    async def test_process_creates_the_session_and_queues_it(
        self, manager_client: AsyncClient, seed: Seed, db_session: AsyncSession
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        placement = await seed.placement(ann, date(2026, 9, 1))
        folder = await seed.folder("Ann", FolderMatchStatus.MATCHED, ann)
        recording = await seed.recording(folder, "Recording 2026-10-01 10-00-00.webm")

        response = await manager_client.post(
            f"/api/v1/recordings/{recording.id}/process", json={}
        )

        assert response.status_code == 202
        body = response.json()
        assert body["placement_id"] == str(placement.id)
        assert body["source"] == "s3"
        assert body["status"] == "uploaded"
        session_id = uuid.UUID(body["id"])
        assert await db_session.get(Session, session_id) is not None
        assert get_processing_queue().is_queued(session_job(session_id))

    async def test_ambiguous_placement_answers_409_with_the_choices(
        self, manager_client: AsyncClient, seed: Seed
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        a = await seed.placement(ann, date(2026, 9, 1))
        b = await seed.placement(ann, date(2026, 9, 15), date(2026, 12, 31))
        folder = await seed.folder("Ann", FolderMatchStatus.MATCHED, ann)
        recording = await seed.recording(folder, "Recording 2026-10-01 10-00-00.webm")

        response = await manager_client.post(
            f"/api/v1/recordings/{recording.id}/process", json={}
        )

        assert response.status_code == 409
        body = response.json()
        assert "More than one placement" in body["detail"]
        assert {p["id"] for p in body["placements"]} == {str(a.id), str(b.id)}
        assert body["placements"][0]["client_name"] == "Northwind"
        assert body["placements"][0]["project_name"] == "Data platform"

        chosen = await manager_client.post(
            f"/api/v1/recordings/{recording.id}/process",
            json={"placement_id": str(b.id)},
        )
        assert chosen.status_code == 202
        assert chosen.json()["placement_id"] == str(b.id)

        again = await manager_client.post(
            f"/api/v1/recordings/{recording.id}/process",
            json={"placement_id": str(b.id)},
        )
        assert again.status_code == 409
        assert "already session" in again.json()["detail"]

    async def test_scoped_roles_cannot_process(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post(
            f"/api/v1/recordings/{uuid.uuid4()}/process", json={}
        )
        assert response.status_code == 403


class TestUploadAndUrl:
    async def test_upload_stores_the_recording_and_queues_it(
        self,
        manager_client: AsyncClient,
        seed: Seed,
        db_session: AsyncSession,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "storage_backend", "local")
        monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
        ann = await seed.consultant("Ann Brooks")
        placement = await seed.placement(ann, date(2026, 1, 1))

        response = await manager_client.post(
            "/api/v1/sessions/upload",
            files={"file": ("check-in.webm", WEBM, "video/webm")},
            data={
                "placement_id": str(placement.id),
                "held_at": "2026-10-01T10:00:00+01:00",
            },
        )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["source"] == "upload"
        assert body["held_at"].startswith("2026-10-01T09:00:00")
        session = await db_session.get(Session, uuid.UUID(body["id"]))
        assert session is not None and session.recording_key is not None
        assert (tmp_path / session.recording_key).read_bytes() == WEBM
        assert get_processing_queue().is_queued(session_job(session.id))

    async def test_upload_needs_a_time_zone_on_held_at(
        self, manager_client: AsyncClient, seed: Seed
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        placement = await seed.placement(ann, date(2026, 1, 1))

        response = await manager_client.post(
            "/api/v1/sessions/upload",
            files={"file": ("check-in.webm", WEBM, "video/webm")},
            data={"placement_id": str(placement.id), "held_at": "2026-10-01T10:00:00"},
        )
        assert response.status_code == 422

    async def test_url_session_is_checked_and_queued(
        self,
        manager_client: AsyncClient,
        seed: Seed,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def check(self: UrlDownloadService, url: str) -> UrlCheck:
            return UrlCheck("call.webm", "video/webm", 1000)

        monkeypatch.setattr(UrlDownloadService, "validate_url", check)
        ann = await seed.consultant("Ann Brooks")
        placement = await seed.placement(ann, date(2026, 1, 1))

        response = await manager_client.post(
            "/api/v1/sessions/url",
            json={
                "url": "https://media.example.com/call.webm",
                "placement_id": str(placement.id),
                "held_at": "2026-10-01T10:00:00+01:00",
            },
        )

        assert response.status_code == 202, response.text
        session_id = uuid.UUID(response.json()["id"])
        assert response.json()["source"] == "url"
        assert get_processing_queue().is_queued(session_job(session_id))

    async def test_private_url_is_refused(
        self, manager_client: AsyncClient, seed: Seed, db_session: AsyncSession
    ) -> None:
        ann = await seed.consultant("Ann Brooks")
        placement = await seed.placement(ann, date(2026, 1, 1))

        response = await manager_client.post(
            "/api/v1/sessions/url",
            json={
                "url": "https://169.254.169.254/latest/meta-data/",
                "placement_id": str(placement.id),
                "held_at": "2026-10-01T10:00:00+01:00",
            },
        )

        assert response.status_code == 422
        assert "private or internal" in response.json()["detail"]
        assert await db_session.scalar(select(Session)) is None

    async def test_scoped_roles_cannot_create_sessions(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post(
            "/api/v1/sessions/url",
            json={
                "url": "https://media.example.com/call.webm",
                "placement_id": str(uuid.uuid4()),
                "held_at": "2026-10-01T10:00:00+01:00",
            },
        )
        assert response.status_code == 403
