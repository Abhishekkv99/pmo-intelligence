"""The PMO recordings folder: Admin > Recordings.

For the global roles. The folder is cataloged by the scanner; here a person
sees the folders tied to a consultant (or needing a choice), settles a
folder's consultant, asks for a scan, and presses Process on a recording,
which creates its session and queues its job.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.dependencies import DbSession, require_roles
from app.models.enums import Role
from app.rate_limiter import limiter
from app.schemas.recordings import (
    ChooseConsultant,
    PlacementChoice,
    ProcessRecording,
    RecordingFolderList,
    ScanRequested,
    SessionCreated,
)
from app.services.recordings.catalog import RecordingCatalog
from app.services.recordings.periodic import request_scan
from app.services.session_service import (
    PlacementChoiceError,
    SessionService,
    enqueue_session,
)

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]


@router.get(
    "/recording-folders", response_model=RecordingFolderList, dependencies=ADMINS
)
async def list_recording_folders(db: DbSession) -> RecordingFolderList:
    """Folders with a consultant or candidates, their recordings, the last scan."""
    return await RecordingCatalog(db).list_folders()


@router.put(
    "/recording-folders/{folder_id}/consultant",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMINS,
)
async def choose_folder_consultant(
    folder_id: uuid.UUID, body: ChooseConsultant, db: DbSession
) -> Response:
    """Tie the folder to a consultant; the scan never changes it afterwards."""
    await RecordingCatalog(db).choose_consultant(folder_id, body.consultant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/recordings/scan",
    response_model=ScanRequested,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def scan_recordings(request: Request) -> ScanRequested:
    """Queue a scan now; ``queued`` is false when one is already queued or running."""
    return ScanRequested(queued=request_scan())


@router.post(
    "/recordings/{recording_id}/process",
    response_model=SessionCreated,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": PlacementChoice}},
    dependencies=ADMINS,
)
@limiter.limit("30/minute")
async def process_recording(
    request: Request,
    recording_id: uuid.UUID,
    body: ProcessRecording,
    db: DbSession,
) -> SessionCreated | JSONResponse:
    """Create the recording's session and queue it for transcription.

    409 with ``placements`` when no single placement of the folder's
    consultant covers the call's date: send one of them as ``placement_id``.
    """
    try:
        session = await SessionService(db).create_from_recording(
            recording_id, body.placement_id
        )
    except PlacementChoiceError as exc:
        options = await RecordingCatalog(db).placement_options(exc.placement_ids)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=PlacementChoice(detail=exc.message, placements=options).model_dump(
                mode="json"
            ),
        )
    # Committed before queueing: the worker reads the row in its own session.
    await db.commit()
    enqueue_session(session.id)
    return SessionCreated.model_validate(session)
