"""The recordings scanner against a real database and a fake bucket.

Pins what the plan promises: folders and recordings are cataloged, folders
are tied to consultants by name, unresolved folders are re-tried as the
register grows, a person's choice is never overwritten, nothing is ever
processed, and every pass leaves a ``recording_scans`` row saying how it
ended. Folder names are synthetic, in the surveyed shapes.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.recording_repo import RecordingRepository
from app.models.enums import FolderMatchStatus, ScanStatus
from app.models.register import Consultant
from app.models.session import (
    RecordingFolder,
    RecordingScan,
    Session,
    SourceRecording,
)
from app.services.processing_queue import get_processing_queue
from app.services.recordings.scanner import (
    RecordingScanner,
    SourceObject,
    group_by_folder,
)

PREFIX = "recordings/pmo/"
MODIFIED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

ROOM_ANN = f"{PREFIX}14-09-26 - PMO support Ann#-#123456#-#PMO#-#UK/"
ROOM_PRIYA = f"{PREFIX}PRJ ITC BD – Priya – Northwind - 1-9-26 - 31-3-27/"
ROOM_RAVI = f"{PREFIX}Ravi onboarding/"
ROOM_NOBODY = f"{PREFIX}PRJ ITC DS - team call/"


def _obj(key: str, size: int = 1000) -> SourceObject:
    return SourceObject(key=key, size=size, last_modified=MODIFIED)


class FakeSource:
    def __init__(self, keys: list[str]) -> None:
        self.objects = [_obj(k) for k in keys]
        self.fail: Exception | None = None

    async def list_objects(self, bucket: str, prefix: str) -> list[SourceObject]:
        if self.fail:
            raise self.fail
        return [o for o in self.objects if o.key.startswith(prefix)]


async def _consultants(db: AsyncSession, *names: str) -> dict[str, Consultant]:
    rows = {name: Consultant(full_name=name) for name in names}
    db.add_all(rows.values())
    await db.flush()
    return rows


async def _folder(db: AsyncSession, key: str) -> RecordingFolder:
    folder = await db.scalar(
        select(RecordingFolder).where(RecordingFolder.folder_key == key)
    )
    assert folder is not None
    await db.refresh(folder)
    return folder


async def _count(db: AsyncSession, model: type) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


@pytest.fixture
def source() -> FakeSource:
    return FakeSource(
        [
            f"{ROOM_ANN}Recording 2026-09-14 10-00-00.webm",
            f"{ROOM_ANN}Recording 2026-09-21 10-00-00.webm",
            f"{ROOM_PRIYA}Recording 2026-10-01 15-30-00.webm",
            f"{ROOM_PRIYA}V1_2026-10-02T093000.mp4",
            f"{ROOM_PRIYA}notes.txt",
            f"{ROOM_PRIYA}old/2025/backup/x/Recording 2025-01-01 10-00-00.webm",
            f"{ROOM_NOBODY}Recording 2026-10-03 11-00-00.webm",
            f"{PREFIX}stray.webm",
        ]
    )


class TestGroupByFolder:
    def test_recordings_are_allowed_files_directly_in_a_folder(
        self, source: FakeSource
    ) -> None:
        grouped = group_by_folder(source.objects, PREFIX, [".webm", ".mp4"])
        assert set(grouped) == {ROOM_ANN, ROOM_PRIYA, ROOM_NOBODY}
        assert [o.key.rsplit("/", 1)[-1] for o in grouped[ROOM_PRIYA]] == [
            "Recording 2026-10-01 15-30-00.webm",
            "V1_2026-10-02T093000.mp4",
        ]


class TestFirstScan:
    async def test_catalogs_folders_and_recordings_and_matches_by_name(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        people = await _consultants(
            db_session, "Ann Brooks", "Priya Shah", "Priya Patel"
        )

        scan = await RecordingScanner(db_session, source).run()

        assert scan.status == ScanStatus.COMPLETED.value
        assert scan.finished_at is not None
        assert (scan.folders_seen, scan.folders_added, scan.folders_matched) == (
            3,
            3,
            1,
        )
        assert (scan.recordings_seen, scan.recordings_added) == (5, 5)

        ann = await _folder(db_session, ROOM_ANN)
        assert ann.match_status == FolderMatchStatus.MATCHED.value
        assert ann.consultant_id == people["Ann Brooks"].id
        assert ann.display_name == "14-09-26 - PMO support Ann"
        assert ann.folder_date is not None

        priya = await _folder(db_session, ROOM_PRIYA)
        assert priya.match_status == FolderMatchStatus.NEEDS_CHOICE.value
        assert priya.consultant_id is None
        assert set(priya.candidate_consultant_ids) == {
            str(people["Priya Shah"].id),
            str(people["Priya Patel"].id),
        }

        nobody = await _folder(db_session, ROOM_NOBODY)
        assert nobody.match_status == FolderMatchStatus.UNMATCHED.value

        recording = await db_session.scalar(
            select(SourceRecording).where(
                SourceRecording.object_key == f"{ROOM_PRIYA}V1_2026-10-02T093000.mp4"
            )
        )
        assert recording is not None
        assert recording.folder_id == priya.id
        assert recording.recorded_at == datetime(2026, 10, 2, 8, 30, tzinfo=UTC)
        assert recording.last_modified == MODIFIED

    async def test_nothing_is_processed_or_queued(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        await _consultants(db_session, "Ann Brooks")

        await RecordingScanner(db_session, source).run()

        assert await _count(db_session, Session) == 0
        assert get_processing_queue().snapshot().depth == 0


class TestLaterScans:
    async def test_new_file_in_a_known_room_is_added_once(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        await _consultants(db_session, "Ann Brooks")
        await RecordingScanner(db_session, source).run()
        source.objects.append(_obj(f"{ROOM_ANN}Recording 2026-09-28 10-00-00.webm"))

        scan = await RecordingScanner(db_session, source).run()
        again = await RecordingScanner(db_session, source).run()

        assert (scan.folders_added, scan.recordings_added) == (0, 1)
        assert again.recordings_added == 0
        assert await _count(db_session, SourceRecording) == 6
        assert (await _folder(db_session, ROOM_ANN)).last_seen_at >= scan.started_at

    async def test_unmatched_folder_matches_once_the_consultant_is_registered(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        source.objects.append(_obj(f"{ROOM_RAVI}Recording 2026-10-04 09-00-00.webm"))
        await RecordingScanner(db_session, source).run()
        assert (await _folder(db_session, ROOM_RAVI)).match_status == (
            FolderMatchStatus.UNMATCHED.value
        )

        ravi = (await _consultants(db_session, "Ravi Kumar"))["Ravi Kumar"]
        scan = await RecordingScanner(db_session, source).run()

        folder = await _folder(db_session, ROOM_RAVI)
        assert folder.match_status == FolderMatchStatus.MATCHED.value
        assert folder.consultant_id == ravi.id
        assert scan.folders_matched == 1

    async def test_chosen_and_matched_folders_are_never_rematched(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        people = await _consultants(
            db_session, "Ann Brooks", "Priya Shah", "Priya Patel"
        )
        await RecordingScanner(db_session, source).run()
        priya = await _folder(db_session, ROOM_PRIYA)
        priya.match_status = FolderMatchStatus.CHOSEN.value
        priya.consultant_id = people["Priya Patel"].id
        priya.candidate_consultant_ids = []
        await db_session.flush()

        # A second Ann would make the Ann room ambiguous if it were re-tried.
        await _consultants(db_session, "Ann Clarke")
        await RecordingScanner(db_session, source).run()

        priya = await _folder(db_session, ROOM_PRIYA)
        assert priya.match_status == FolderMatchStatus.CHOSEN.value
        assert priya.consultant_id == people["Priya Patel"].id
        ann = await _folder(db_session, ROOM_ANN)
        assert ann.match_status == FolderMatchStatus.MATCHED.value
        assert ann.consultant_id == people["Ann Brooks"].id


class TestFailedScans:
    async def test_failure_is_recorded_and_the_catalog_is_unchanged(
        self, db_session: AsyncSession, source: FakeSource
    ) -> None:
        source.fail = PermissionError("AccessDenied on ListObjectsV2")

        scan = await RecordingScanner(db_session, source).run()

        assert scan.status == ScanStatus.FAILED.value
        assert scan.error_message == ("PermissionError: AccessDenied on ListObjectsV2")
        assert scan.finished_at is not None
        assert await _count(db_session, RecordingFolder) == 0

    async def test_takeover_sweep_fails_scans_left_running(
        self, db_session: AsyncSession
    ) -> None:
        repo = RecordingRepository(db_session)
        left = await repo.start_scan(datetime(2026, 10, 8, 9, 0, tzinfo=UTC))

        count = await repo.fail_running_scans(
            datetime(2026, 10, 8, 9, 5, tzinfo=UTC), "Interrupted"
        )

        assert count == 1
        await db_session.refresh(left)
        assert left.status == ScanStatus.FAILED.value
        assert left.error_message == "Interrupted"
        latest = await repo.latest_scan()
        assert latest is not None and latest.id == left.id
        assert await _count(db_session, RecordingScan) == 1
