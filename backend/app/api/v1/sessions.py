"""Recorded sessions: creating one, the sessions list and the session page.

Creating a session (upload, URL), retrying one and correcting its kind are for
the global roles; the placement and the time of the call come from the form.
Creating answers 202 once the session exists and its job is queued: an upload
is already stored, a URL is checked and downloaded by the job.

Reading is for anyone whose scope covers the session's placement: the list
shows only those sessions, and a by-id route answers 404 outside scope. Only
the session page itself writes an ``access_log`` row.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import AwareDatetime

from app.dependencies import (
    DbSession,
    LoggedSessionScope,
    SessionScope,
    get_current_user,
    require_media_token,
    require_roles,
)
from app.models.enums import Role, SessionStatus
from app.models.user import User
from app.rate_limiter import limiter
from app.schemas.recordings import SessionCreated, UrlSessionCreate
from app.schemas.sessions import KindUpdate, MediaUrl, SessionDetail, SessionListItem
from app.services.media_token import MEDIA_URL_SECONDS
from app.services.session_service import SessionService, enqueue_session
from app.services.session_view import SessionViewService

router = APIRouter()

ADMINS = [Depends(require_roles(Role.PMO_MANAGER, Role.ADMIN))]
# Any role may list; the list itself is cut to the caller's scope.
ANY_ROLE = require_roles(*Role)

# Also the path the upload body limit (app.middleware.body_limit) guards.
UPLOAD_PATH = "/sessions/upload"
MEDIA_ROUTE_NAME = "session_media"


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


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    db: DbSession,
    current_user: User = Depends(ANY_ROLE),
    consultant_id: uuid.UUID | None = None,
    status: SessionStatus | None = None,
) -> list[SessionListItem]:
    """The sessions in the caller's scope, newest call first."""
    return await SessionViewService(db).list_sessions(
        current_user, consultant_id=consultant_id, status=status
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session: LoggedSessionScope,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> SessionDetail:
    """The session page: transcript, summary, signals, issues, actions, cost."""
    return await SessionViewService(db).detail(session, current_user)


@router.get("/sessions/{session_id}/media-url", response_model=MediaUrl)
async def get_media_url(
    request: Request, session: SessionScope, db: DbSession
) -> MediaUrl:
    """A 15-minute URL the audio player can read the recording from."""
    access = await SessionViewService(db).media_access(session)
    url = access.url
    if url is None:
        url = str(
            request.url_for(
                MEDIA_ROUTE_NAME, session_id=session.id
            ).include_query_params(token=access.token)
        )
    return MediaUrl(
        url=url,
        content_type=access.content_type,
        expires_in_seconds=MEDIA_URL_SECONDS,
    )


@router.get(
    "/sessions/{session_id}/media",
    name=MEDIA_ROUTE_NAME,
    response_class=FileResponse,
)
async def get_media(
    db: DbSession, session_id: uuid.UUID = Depends(require_media_token)
) -> FileResponse:
    """The stored recording on local storage, with Range support; 404 on S3."""
    path, content_type = await SessionViewService(db).local_media(session_id)
    return FileResponse(path, media_type=content_type)


@router.patch(
    "/sessions/{session_id}/kind",
    response_model=SessionDetail,
    dependencies=ADMINS,
)
async def set_session_kind(
    body: KindUpdate,
    session: SessionScope,
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> SessionDetail:
    """Correct the kind of call; a later analysis keeps it."""
    await SessionService(db).set_kind(session, body.kind, current_user.id)
    return await SessionViewService(db).detail(session, current_user)


@router.post(
    "/sessions/{session_id}/retry",
    response_model=SessionCreated,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=ADMINS,
)
@limiter.limit("10/minute")
async def retry_session(
    request: Request, session: SessionScope, db: DbSession
) -> SessionCreated:
    """Queue a failed session again from where it failed."""
    await SessionService(db).retry(session)
    await db.commit()
    enqueue_session(session.id)
    return SessionCreated.model_validate(session)
