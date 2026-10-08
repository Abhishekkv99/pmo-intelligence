"""Unit tests for authentication service (JWT, password hashing)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.config import settings
from app.schemas.auth import UserRegister
from app.services.auth_service import AuthService, password_hash
from app.utils.exceptions import AuthenticationError, AuthorizationError


class TestPasswordHashing:
    """Tests for password hash and verify."""

    def test_hash_and_verify_password(self) -> None:
        raw = "MySecurePassword123"
        hashed = password_hash.hash(raw)
        assert hashed != raw
        assert password_hash.verify(raw, hashed)

    def test_wrong_password_fails_verify(self) -> None:
        hashed = password_hash.hash("correct-password")
        assert not password_hash.verify("wrong-password", hashed)


class TestCreateAccessToken:
    """Tests for JWT access token creation."""

    def test_creates_valid_jwt(self) -> None:
        user_id = uuid.uuid4()
        token = AuthService.create_access_token(user_id)

        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        assert payload["sub"] == str(user_id)
        assert "exp" in payload
        assert "iat" in payload

    def test_token_has_correct_expiry(self) -> None:
        user_id = uuid.uuid4()
        before = datetime.now(UTC)
        token = AuthService.create_access_token(user_id)
        after = datetime.now(UTC)

        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        # JWT exp is integer seconds — allow 1-second tolerance
        expected_min = (
            before
            + timedelta(minutes=settings.access_token_expiration_minutes)
            - timedelta(seconds=1)
        )
        expected_max = (
            after
            + timedelta(minutes=settings.access_token_expiration_minutes)
            + timedelta(seconds=1)
        )
        assert expected_min <= exp <= expected_max


class TestDecodeAccessToken:
    """Tests for JWT access token decoding."""

    def test_decode_valid_token(self) -> None:
        user_id = uuid.uuid4()
        token = AuthService.create_access_token(user_id)
        decoded_id = AuthService.decode_access_token(token)
        assert decoded_id == user_id

    def test_decode_expired_token_raises(self) -> None:
        user_id = uuid.uuid4()
        expired_payload = {
            "sub": str(user_id),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=2),
        }
        token = jwt.encode(
            expired_payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(AuthenticationError, match="expired"):
            AuthService.decode_access_token(token)

    def test_decode_invalid_token_raises(self) -> None:
        with pytest.raises(AuthenticationError, match="Invalid token"):
            AuthService.decode_access_token("not.a.valid.token")

    def test_decode_token_missing_subject_raises(self) -> None:
        payload = {
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
        }
        token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(AuthenticationError, match="missing subject"):
            AuthService.decode_access_token(token)


class TestRegister:
    """Tests for user registration."""

    async def test_register_creates_user(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        mock_user = MagicMock()
        mock_user.email = "new@example.com"

        with (
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(
                service.user_repo, "create", return_value=mock_user
            ) as mock_create,
        ):
            data = UserRegister(
                email="new@example.com",
                password="securePass1",
                full_name="New User",
            )
            result = await service.register(data)

        assert result.email == "new@example.com"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["email"] == "new@example.com"
        assert call_kwargs["full_name"] == "New User"
        assert call_kwargs["hashed_password"] != "securePass1"
        # Created with no role: a new account reads nothing until granted.
        assert "role" not in call_kwargs

    async def test_register_elevates_bootstrap_admin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "Boss@Example.com")
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        mock_user = MagicMock()
        mock_user.email = "boss@example.com"
        mock_user.role = None

        with (
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(service.user_repo, "create", return_value=mock_user),
        ):
            data = UserRegister(
                email="boss@example.com",
                password="securePass1",
                full_name="Boss",
            )
            result = await service.register(data)

        assert result is mock_user
        assert mock_user.role == "pmo_manager"
        mock_session.flush.assert_awaited_once()

    async def test_register_duplicate_email_raises(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        existing_user = MagicMock()
        with patch.object(
            service.user_repo, "get_by_email", return_value=existing_user
        ):
            data = UserRegister(
                email="taken@example.com",
                password="securePass1",
                full_name="Duplicate User",
            )
            with pytest.raises(AuthenticationError, match="already registered"):
                await service.register(data)

    async def test_register_leaves_an_unlisted_user_without_a_role(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "someone@else.com")
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        mock_user = MagicMock()
        mock_user.email = "jane@example.com"
        mock_user.role = None

        with (
            patch.object(service.user_repo, "get_by_email", return_value=None),
            patch.object(service.user_repo, "create", return_value=mock_user),
        ):
            data = UserRegister(
                email="jane@example.com",
                password="securePass1",
                full_name="Jane",
            )
            await service.register(data)

        assert mock_user.role is None
        mock_session.flush.assert_not_awaited()


class TestAuthenticate:
    """Tests for user authentication."""

    async def test_authenticate_valid_credentials(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        hashed = password_hash.hash("correctPassword")
        mock_user = MagicMock()
        mock_user.hashed_password = hashed
        mock_user.is_active = True
        mock_user.role = "tech_lead"

        with patch.object(service.user_repo, "get_by_email", return_value=mock_user):
            result = await service.authenticate("user@example.com", "correctPassword")
        assert result == mock_user

    async def test_authenticate_user_without_a_role_is_refused(self) -> None:
        """The same rule as SSO: no role, no session, even with the password."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        mock_user = MagicMock()
        mock_user.hashed_password = password_hash.hash("correctPassword")
        mock_user.is_active = True
        mock_user.role = None

        with (
            patch.object(service.user_repo, "get_by_email", return_value=mock_user),
            pytest.raises(AuthorizationError, match="has not been given access"),
        ):
            await service.authenticate("user@example.com", "correctPassword")

    async def test_authenticate_wrong_password_raises(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        hashed = password_hash.hash("correctPassword")
        mock_user = MagicMock()
        mock_user.hashed_password = hashed
        mock_user.is_active = True

        with (
            patch.object(service.user_repo, "get_by_email", return_value=mock_user),
            pytest.raises(AuthenticationError, match="Invalid email or password"),
        ):
            await service.authenticate("user@example.com", "wrongPassword")

    async def test_authenticate_nonexistent_user_raises(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        with (
            patch.object(service.user_repo, "get_by_email", return_value=None),
            pytest.raises(AuthenticationError, match="Invalid email or password"),
        ):
            await service.authenticate("nobody@example.com", "anyPassword")

    async def test_authenticate_sso_only_user_raises(self) -> None:
        """SSO-only users (no password) cannot use email/password login."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        sso_user = MagicMock()
        sso_user.hashed_password = None
        sso_user.is_active = True
        sso_user.auth_provider = "microsoft_entra"

        with (
            patch.object(service.user_repo, "get_by_email", return_value=sso_user),
            pytest.raises(AuthenticationError, match="SSO"),
        ):
            await service.authenticate("sso@example.com", "anyPassword")

    async def test_authenticate_inactive_user_raises(self) -> None:
        """Inactive users are rejected even with correct password."""
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        hashed = password_hash.hash("correctPassword")
        inactive_user = MagicMock()
        inactive_user.hashed_password = hashed
        inactive_user.is_active = False
        inactive_user.role = "sme"

        with (
            patch.object(service.user_repo, "get_by_email", return_value=inactive_user),
            pytest.raises(AuthorizationError, match="has not been given access"),
        ):
            await service.authenticate("inactive@example.com", "correctPassword")
