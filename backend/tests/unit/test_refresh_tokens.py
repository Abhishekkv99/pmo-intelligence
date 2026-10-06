"""Unit tests for refresh token service methods."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.refresh_token import RefreshToken
from app.services.auth_service import AuthService
from app.utils.exceptions import AuthenticationError


class TestCreateRefreshToken:
    """Tests for refresh token generation."""

    def test_creates_url_safe_string(self) -> None:
        token = AuthService.create_refresh_token()
        assert isinstance(token, str)
        assert len(token) > 40

    def test_tokens_are_unique(self) -> None:
        tokens = {AuthService.create_refresh_token() for _ in range(100)}
        assert len(tokens) == 100


class TestHashToken:
    """Tests for token hashing."""

    def test_hash_is_sha256_hex(self) -> None:
        token = "test-token-value"
        hashed = AuthService.hash_token(token)
        assert len(hashed) == 64
        assert all(c in "0123456789abcdef" for c in hashed)

    def test_same_input_same_hash(self) -> None:
        token = "deterministic-input"
        assert AuthService.hash_token(token) == AuthService.hash_token(token)

    def test_different_input_different_hash(self) -> None:
        assert AuthService.hash_token("token-a") != AuthService.hash_token("token-b")


class TestStoreRefreshToken:
    """Tests for storing refresh tokens in the database."""

    async def test_stores_hashed_token(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()
        raw_token = "raw-token-value"

        result = await service.store_refresh_token(user_id, raw_token)

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, RefreshToken)
        assert added_obj.user_id == user_id
        assert added_obj.token_hash == AuthService.hash_token(raw_token)
        assert added_obj.is_revoked in (False, None)  # default applied at DB level
        assert added_obj.expires_at > datetime.now(UTC)
        mock_session.flush.assert_awaited_once()
        assert result is added_obj


class TestValidateAndRotateRefreshToken:
    """Tests for refresh token validation and rotation."""

    async def test_valid_token_returns_user_id_and_revokes(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()
        raw_token = "valid-token"

        mock_refresh = MagicMock(spec=RefreshToken)
        mock_refresh.user_id = user_id
        mock_refresh.is_revoked = False
        mock_refresh.expires_at = datetime.now(UTC) + timedelta(days=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_refresh
        mock_session.execute.return_value = mock_result

        returned_user_id = await service.validate_and_rotate_refresh_token(raw_token)

        assert returned_user_id == user_id
        assert mock_refresh.is_revoked is True
        mock_session.flush.assert_awaited()

    async def test_invalid_token_raises(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            await service.validate_and_rotate_refresh_token("bad-token")

    async def test_expired_token_revokes_and_raises(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)

        mock_refresh = MagicMock(spec=RefreshToken)
        mock_refresh.is_revoked = False
        mock_refresh.expires_at = datetime.now(UTC) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_refresh
        mock_session.execute.return_value = mock_result

        with pytest.raises(AuthenticationError, match="expired"):
            await service.validate_and_rotate_refresh_token("expired-token")
        assert mock_refresh.is_revoked is True


class TestRevokeAllUserTokens:
    """Tests for revoking all user refresh tokens (logout)."""

    async def test_revokes_all_active_tokens(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await service.revoke_all_user_tokens(user_id)

        assert count == 3
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()

    async def test_returns_zero_when_no_tokens(self) -> None:
        mock_session = AsyncMock()
        service = AuthService(mock_session)
        user_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await service.revoke_all_user_tokens(user_id)

        assert count == 0


class TestAccessTokenUsesShortExpiry:
    """Verify access token uses the new shorter expiry setting."""

    def test_access_token_expiry_uses_config(self) -> None:
        user_id = uuid.uuid4()
        before = datetime.now(UTC)
        token = AuthService.create_access_token(user_id)

        import jwt as pyjwt

        from app.config import settings

        payload = pyjwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected = before + timedelta(minutes=settings.access_token_expiration_minutes)
        # Allow 2-second tolerance
        assert abs((exp - expected).total_seconds()) < 2
