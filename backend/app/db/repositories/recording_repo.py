"""Queries for the recordings folder catalog and its scans."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ScanStatus
from app.models.session import RecordingFolder, RecordingScan, SourceRecording


class RecordingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def folders_by_key(self) -> dict[str, RecordingFolder]:
        result = await self.session.execute(select(RecordingFolder))
        return {folder.folder_key: folder for folder in result.scalars()}

    async def recording_keys(self) -> set[str]:
        result = await self.session.execute(select(SourceRecording.object_key))
        return set(result.scalars())

    async def get_recording(
        self, recording_id: uuid.UUID
    ) -> tuple[SourceRecording, RecordingFolder] | None:
        """A recording with its folder."""
        result = await self.session.execute(
            select(SourceRecording, RecordingFolder)
            .join(RecordingFolder, SourceRecording.folder_id == RecordingFolder.id)
            .where(SourceRecording.id == recording_id)
        )
        row = result.one_or_none()
        return None if row is None else (row[0], row[1])

    def add(self, row: RecordingFolder | SourceRecording) -> None:
        self.session.add(row)

    async def flush(self) -> None:
        await self.session.flush()

    async def start_scan(self, started_at: datetime) -> RecordingScan:
        scan = RecordingScan(started_at=started_at, status=ScanStatus.RUNNING.value)
        self.session.add(scan)
        await self.session.flush()
        return scan

    async def finish_scan(
        self,
        scan_id: uuid.UUID,
        *,
        finished_at: datetime,
        status: ScanStatus,
        error_message: str | None = None,
        **counts: int,
    ) -> None:
        await self.session.execute(
            update(RecordingScan)
            .where(RecordingScan.id == scan_id)
            .values(
                finished_at=finished_at,
                status=status.value,
                error_message=error_message,
                **counts,
            )
        )

    async def latest_scan(self) -> RecordingScan | None:
        result = await self.session.execute(
            select(RecordingScan).order_by(RecordingScan.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def fail_running_scans(self, finished_at: datetime, reason: str) -> int:
        """Mark every scan still ``running`` as failed; returns how many."""
        result = await self.session.execute(
            update(RecordingScan)
            .where(RecordingScan.status == ScanStatus.RUNNING.value)
            .values(
                status=ScanStatus.FAILED.value,
                finished_at=finished_at,
                error_message=reason,
            )
            .returning(RecordingScan.id)
        )
        return len(result.all())
