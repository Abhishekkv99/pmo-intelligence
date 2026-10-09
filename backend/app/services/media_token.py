"""Short-lived tokens that let the browser play a session's recording locally.

An ``<audio>`` tag cannot send the Bearer token, so on local storage the
session page is given a URL carrying one of these instead. The token names
one session and expires after ``MEDIA_URL_SECONDS``; it is signed with
``SECRET_KEY`` under its own audience, so it is never accepted as an access
token, nor an access token as one of these. On S3 the page gets a presigned
URL and this token is not used.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from app.utils.exceptions import NotFoundError

MEDIA_URL_SECONDS = 15 * 60
MEDIA_AUDIENCE = "session-media"


def create_media_token(session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(session_id),
        "aud": MEDIA_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=MEDIA_URL_SECONDS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def check_media_token(token: str, session_id: uuid.UUID) -> None:
    """Raise ``NotFoundError`` unless ``token`` is valid for ``session_id``.

    A bad, expired or other session's token answers exactly as a missing
    session does, like every other denied by-id read.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=MEDIA_AUDIENCE,
            options={"require": ["sub", "aud", "exp"]},
        )
    except jwt.InvalidTokenError as err:
        raise NotFoundError("Session", str(session_id)) from err
    if payload["sub"] != str(session_id):
        raise NotFoundError("Session", str(session_id))
