"""Recorded sessions: creating one from an upload or a URL.

For the global roles; the placement and the time of the call come from the
form. Both answer 202 once the session exists and its job is queued: an
upload is already stored, a URL is checked and downloaded by the job.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import AwareDatetime

from app.dependencies import DbSession, require_roles
from app.models.enums import Role
from app.rate_limiter import limiter
from app.schemas.recordings import SessionCreated, UrlSessionCreate
from app.services.session_service import SessionService, enqueue_session

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]

# Also the path the upload body limit (app.middleware.body_limit) guards.
UPLOAD_PATH = "/sessions/upload"


@router.post(
    UPLOAD_PATH,
    response_model=SessionCreated,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def upload_session(
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
    placement_id: uuid.UUID = Form(...),
    held_at: AwareDatetime = Form(...),
) -> SessionCreated:
    """Store an uploaded recording as a new session and queue its transcription."""
    session = await SessionService(db).create_from_upload(file, placement_id, held_at)
    # Committed before queueing: the worker reads the row in its own session.
    await db.commit()
    enqueue_session(session.id)
    return SessionCreated.model_validate(session)


@router.post(
    "/sessions/url",
    response_model=SessionCreated,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def url_session(
    request: Request, body: UrlSessionCreate, db: DbSession
) -> SessionCreated:
    """Check a recording URL, create its session and queue the download."""
    session = await SessionService(db).create_from_url(
        str(body.url), body.placement_id, body.held_at
    )
    await db.commit()
    enqueue_session(session.id)
    return SessionCreated.model_validate(session)
