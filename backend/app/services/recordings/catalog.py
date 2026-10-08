"""The recordings folder as the Admin page sees it, and a person's choices on it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.consultant_repo import ConsultantRepository
from app.db.repositories.placement_repo import PlacementRepository
from app.db.repositories.recording_repo import RecordingRepository
from app.models.enums import FolderMatchStatus, PlacementStatus, SessionStatus
from app.models.session import RecordingFolder
from app.schemas.recordings import (
    ConsultantRef,
    PlacementOption,
    RecordingFolderItem,
    RecordingFolderList,
    RecordingItem,
    RecordingSessionRef,
    ScanSummary,
)
from app.utils.exceptions import NotFoundError, ValidationError


class RecordingCatalog:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.recordings = RecordingRepository(db)
        self.consultants = ConsultantRepository(db)
        self.placements = PlacementRepository(db)

    async def list_folders(self) -> RecordingFolderList:
        """Every folder with a consultant or candidates, with its recordings.

        Unmatched folders are left out: nobody can process them until the
        register holds a consultant whose name they carry.
        """
        folders = await self.recordings.listed_folders()
        names = {c.id: c.full_name for c in await self.consultants.list_by_name()}
        rows = await self.recordings.recordings_with_sessions([f.id for f in folders])
        by_folder: dict[uuid.UUID, list[RecordingItem]] = {f.id: [] for f in folders}
        for recording, session_id, session_status in rows:
            by_folder[recording.folder_id].append(
                RecordingItem(
                    id=recording.id,
                    filename=recording.object_key.rsplit("/", 1)[-1],
                    size_bytes=recording.size_bytes,
                    recorded_at=recording.recorded_at or recording.last_modified,
                    time_from_name=recording.recorded_at is not None,
                    session=(
                        RecordingSessionRef(
                            id=session_id, status=SessionStatus(session_status)
                        )
                        if session_id is not None and session_status is not None
                        else None
                    ),
                )
            )

        def ref(consultant_id: uuid.UUID | None) -> ConsultantRef | None:
            if consultant_id is None or consultant_id not in names:
                return None
            return ConsultantRef(id=consultant_id, full_name=names[consultant_id])

        items = []
        for folder in folders:
            candidates = [ref(uuid.UUID(c)) for c in folder.candidate_consultant_ids]
            items.append(
                RecordingFolderItem(
                    id=folder.id,
                    display_name=folder.display_name,
                    folder_date=folder.folder_date,
                    match_status=FolderMatchStatus(folder.match_status),
                    consultant=ref(folder.consultant_id),
                    candidates=[c for c in candidates if c is not None],
                    last_seen_at=folder.last_seen_at,
                    recordings=by_folder[folder.id],
                )
            )
        latest = await self.recordings.latest_scan()
        return RecordingFolderList(
            folders=items,
            latest_scan=ScanSummary.model_validate(latest) if latest else None,
            scan_enabled=settings.recordings_scan_enabled,
            scan_interval_seconds=settings.recordings_scan_interval_seconds,
        )

    async def choose_consultant(
        self, folder_id: uuid.UUID, consultant_id: uuid.UUID
    ) -> RecordingFolder:
        """A person ties the folder to a consultant; later scans keep it.

        Any consultant may be chosen, to settle a folder that names several
        or to correct a wrong automatic match. Sessions already made from the
        folder keep their placement.
        """
        folder = await self.recordings.get_folder(folder_id)
        if folder is None:
            raise NotFoundError("Recording folder", str(folder_id))
        if await self.consultants.get_by_id(consultant_id) is None:
            raise ValidationError("That consultant is not in the register")
        folder.consultant_id = consultant_id
        folder.match_status = FolderMatchStatus.CHOSEN.value
        folder.candidate_consultant_ids = []
        await self.db.flush()
        return folder

    async def placement_options(
        self, placement_ids: list[uuid.UUID]
    ) -> list[PlacementOption]:
        options = []
        for placement_id in placement_ids:
            row = await self.placements.get_row(placement_id)
            if row is None:
                continue
            placement = row.placement
            options.append(
                PlacementOption(
                    id=placement.id,
                    client_name=row.client.name,
                    project_name=row.project.name,
                    start_date=placement.start_date,
                    expected_end_date=placement.expected_end_date,
                    status=PlacementStatus(placement.status),
                )
            )
        return options
