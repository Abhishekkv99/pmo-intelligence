"""The audio player's media token: one session, 15 minutes, its own audience."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.services.auth_service import AuthService
from app.services.media_token import (
    MEDIA_AUDIENCE,
    check_media_token,
    create_media_token,
)
from app.utils.exceptions import AuthenticationError, NotFoundError


def _token(**changes: object) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "aud": MEDIA_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    payload.update(changes)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


class TestMediaToken:
    def test_a_fresh_token_opens_its_own_session(self) -> None:
        session_id = uuid.uuid4()
        check_media_token(create_media_token(session_id), session_id)

    def test_another_sessions_token_is_refused_as_not_found(self) -> None:
        with pytest.raises(NotFoundError):
            check_media_token(create_media_token(uuid.uuid4()), uuid.uuid4())

    def test_an_expired_token_is_refused(self) -> None:
        session_id = uuid.uuid4()
        old = datetime.now(UTC) - timedelta(minutes=20)
        token = _token(sub=str(session_id), iat=old, exp=old + timedelta(minutes=15))
        with pytest.raises(NotFoundError):
            check_media_token(token, session_id)

    def test_a_token_signed_with_another_key_is_refused(self) -> None:
        session_id = uuid.uuid4()
        forged = jwt.encode(
            {"sub": str(session_id), "aud": MEDIA_AUDIENCE, "exp": 4_000_000_000},
            "another-key-that-is-long-enough-for-hs256",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(NotFoundError):
            check_media_token(forged, session_id)

    def test_an_access_token_is_not_a_media_token(self) -> None:
        user_id = uuid.uuid4()
        with pytest.raises(NotFoundError):
            check_media_token(AuthService.create_access_token(user_id), user_id)

    def test_a_media_token_is_not_an_access_token(self) -> None:
        with pytest.raises(AuthenticationError):
            AuthService.decode_access_token(create_media_token(uuid.uuid4()))
