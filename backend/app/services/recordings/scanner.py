"""Catalog the PMO recordings folder; never process anything.

One pass lists every object under the prefix, records new folders and new
recording files, ties folders to consultants by name (``name_match``) and
re-tries the folders still unmatched or awaiting a choice, since the
register may have gained the consultant since. A folder a person chose, or
one already matched, is left alone. Nothing is queued for transcription: a
person presses Process for each recording (2,433 recordings were on the
folder when it was surveyed).

Only calls on or after ``RECORDINGS_EARLIEST_DATE`` (a UK date) are
cataloged, and a folder only when it holds at least one of them: older
calls are out of scope. A call's time is the one in its file name, else
its S3 time.

Every pass writes a ``recording_scans`` row. The catalog is written in one
transaction, so a pass that fails or runs past ``SCAN_TIME_LIMIT_SECONDS``
leaves the catalog as it was and records why.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

import aioboto3
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.consultant_repo import ConsultantRepository
from app.db.repositories.recording_repo import RecordingRepository
from app.models.enums import FolderMatchStatus, ScanStatus
from app.models.session import RecordingFolder, RecordingScan, SourceRecording
from app.services.media_files import extension_of
from app.services.recordings.folder_names import (
    local_day,
    parse_folder_name,
    recorded_at_from_filename,
)
from app.services.recordings.name_match import ConsultantName, match_folder

logger = logging.getLogger(__name__)

# A catalog pass over the surveyed folder (about 2,400 objects) takes
# seconds; a pass this long has hung on S3 or the database.
SCAN_TIME_LIMIT_SECONDS = 600

# Folders whose consultant is re-tried on every pass.
REMATCHED = frozenset({FolderMatchStatus.UNMATCHED, FolderMatchStatus.NEEDS_CHOICE})


@dataclass(frozen=True)
class SourceObject:
    key: str
    size: int
    last_modified: datetime


class RecordingSource(Protocol):
    async def list_objects(self, bucket: str, prefix: str) -> list[SourceObject]: ...


class S3RecordingSource:
    """Lists the recordings bucket with the task role (a bucket policy grants it)."""

    async def list_objects(self, bucket: str, prefix: str) -> list[SourceObject]:
        objects: list[SourceObject] = []
        session = aioboto3.Session()
        async with session.client("s3", region_name=settings.aws_region) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    objects.append(
                        SourceObject(
                            key=item["Key"],
                            size=int(item["Size"]),
                            last_modified=item["LastModified"],
                        )
                    )
        return objects


def group_by_folder(
    objects: list[SourceObject], prefix: str, allowed_extensions: list[str]
) -> dict[str, list[SourceObject]]:
    """Folder key → its recording files.

    Every folder with any object in it is listed; a recording is a file with
    an allowed extension directly in its folder. Anything nested deeper, and
    objects straight under the prefix, are ignored.
    """
    folders: dict[str, list[SourceObject]] = defaultdict(list)
    for obj in objects:
        if not obj.key.startswith(prefix):
            continue
        parts = obj.key[len(prefix) :].split("/")
        if len(parts) < 2:
            continue
        folder_key = f"{prefix}{parts[0]}/"
        files = folders[folder_key]
        if (
            len(parts) == 2
            and parts[1]
            and extension_of(parts[1]) in allowed_extensions
        ):
            files.append(obj)
    return dict(folders)


@dataclass(frozen=True)
class TimedRecording:
    obj: SourceObject
    # From the file name; None when the name carries no time.
    recorded_at: datetime | None

    @property
    def call_time(self) -> datetime:
        return self.recorded_at or self.obj.last_modified


def keep_recent(
    grouped: dict[str, list[SourceObject]],
    earliest: date | None,
    timezone: str,
) -> dict[str, list[TimedRecording]]:
    """Folder key to its recordings from ``earliest`` on (a day in ``timezone``).

    A folder without one is left out. ``earliest`` None keeps every folder
    that has a recording, with all of them.
    """
    kept: dict[str, list[TimedRecording]] = {}
    for folder_key, files in grouped.items():
        timed = [
            TimedRecording(
                obj, recorded_at_from_filename(obj.key.rsplit("/", 1)[-1], timezone)
            )
            for obj in files
        ]
        recent = [
            t
            for t in timed
            if earliest is None or local_day(t.call_time, timezone) >= earliest
        ]
        if recent:
            kept[folder_key] = recent
    return kept


@dataclass
class ScanCounts:
    folders_seen: int = 0
    folders_added: int = 0
    folders_matched: int = 0
    recordings_seen: int = 0
    recordings_added: int = 0


class RecordingScanner:
    def __init__(
        self, session: AsyncSession, source: RecordingSource | None = None
    ) -> None:
        self.session = session
        self.source = source or S3RecordingSource()
        self.recordings = RecordingRepository(session)
        self.consultants = ConsultantRepository(session)

    async def run(self) -> RecordingScan:
        """One pass; always ends with its ``recording_scans`` row finished.

        A pass cancelled at shutdown stays ``running`` until the next owner's
        takeover sweep fails it.
        """
        scan = await self.recordings.start_scan(datetime.now(UTC))
        # Read now: the rollback below expires the row.
        scan_id = scan.id
        await self.session.commit()
        try:
            async with asyncio.timeout(SCAN_TIME_LIMIT_SECONDS):
                counts = await self._catalog()
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            reason = (
                f"Stopped after {SCAN_TIME_LIMIT_SECONDS} s"
                if isinstance(exc, TimeoutError)
                else f"{type(exc).__name__}: {exc}"
            )
            logger.exception("Recordings scan %s failed: %s", scan_id, reason)
            await self.recordings.finish_scan(
                scan_id,
                finished_at=datetime.now(UTC),
                status=ScanStatus.FAILED,
                error_message=reason[:2000],
            )
        else:
            logger.info(
                "Recordings scan %s: %d folders (%d new, %d matched), "
                "%d recordings (%d new)",
                scan_id,
                counts.folders_seen,
                counts.folders_added,
                counts.folders_matched,
                counts.recordings_seen,
                counts.recordings_added,
            )
            await self.recordings.finish_scan(
                scan_id,
                finished_at=datetime.now(UTC),
                status=ScanStatus.COMPLETED,
                **vars(counts),
            )
        await self.session.commit()
        await self.session.refresh(scan)
        return scan

    async def _catalog(self) -> ScanCounts:
        prefix = settings.recordings_source_prefix
        objects = await self.source.list_objects(
            settings.recordings_source_bucket, prefix
        )
        grouped = group_by_folder(objects, prefix, settings.allowed_extensions)
        recent = keep_recent(
            grouped, settings.recordings_earliest_date, settings.recordings_timezone
        )
        if len(recent) < len(grouped):
            logger.info(
                "Recordings scan: %d of %d folders have calls on or after %s",
                len(recent),
                len(grouped),
                settings.recordings_earliest_date,
            )
        consultants = [
            ConsultantName(c.id, c.full_name)
            for c in await self.consultants.list_by_name()
        ]
        folders = await self.recordings.folders_by_key()
        known_recordings = await self.recordings.recording_keys()
        now = datetime.now(UTC)
        counts = ScanCounts(folders_seen=len(recent))

        for folder_key, files in recent.items():
            folder = folders.get(folder_key)
            parsed = parse_folder_name(folder_key[len(prefix) : -1])
            if folder is None:
                folder = RecordingFolder(
                    folder_key=folder_key,
                    display_name=parsed.display_name,
                    folder_date=parsed.folder_date,
                    last_seen_at=now,
                )
                self._apply_match(folder, parsed.match_text, consultants, counts)
                self.recordings.add(folder)
                counts.folders_added += 1
            else:
                folder.last_seen_at = now
                if FolderMatchStatus(folder.match_status) in REMATCHED:
                    self._apply_match(folder, parsed.match_text, consultants, counts)
            await self.recordings.flush()

            counts.recordings_seen += len(files)
            for timed in files:
                if timed.obj.key in known_recordings:
                    continue
                self.recordings.add(
                    SourceRecording(
                        folder_id=folder.id,
                        object_key=timed.obj.key,
                        size_bytes=timed.obj.size,
                        last_modified=timed.obj.last_modified,
                        recorded_at=timed.recorded_at,
                    )
                )
                counts.recordings_added += 1
        await self.recordings.flush()
        return counts

    @staticmethod
    def _apply_match(
        folder: RecordingFolder,
        match_text: str,
        consultants: list[ConsultantName],
        counts: ScanCounts,
    ) -> None:
        match = match_folder(match_text, consultants)
        folder.match_status = match.status.value
        folder.consultant_id = match.consultant_id
        folder.candidate_consultant_ids = [str(i) for i in match.candidate_ids]
        if match.status == FolderMatchStatus.MATCHED:
            counts.folders_matched += 1
