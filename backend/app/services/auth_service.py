import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from pwdlib import PasswordHash
from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.db.repositories.user_repo import UserRepository
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import UserRegister
from app.utils.entitlements import (
    assert_may_sign_in,
    elevate_if_bootstrap_admin,
    may_use_app,
)
from app.utils.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

password_hash = PasswordHash.recommended()

# A refused refresh: the session ends and the person signs in again, where a
# refused sign-in says why
SESSION_ENDED_MESSAGE = "Your session has ended. Please sign in again."


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(self, data: UserRegister) -> User:
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise AuthenticationError("Email already registered")
        hashed = password_hash.hash(data.password)
        # No role on creation, as for SSO JIT provisioning — one rule for
        # every row-creation path, and the same bootstrap-admin grant.
        user = await self.user_repo.create(
            email=data.email,
            hashed_password=hashed,
            full_name=data.full_name,
        )
        if elevate_if_bootstrap_admin(user):
            await self.session.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_by_email(email)
        if user is None:
            # Hash a dummy password to prevent timing-based enumeration
            password_hash.hash("dummy-password-for-timing")
            raise AuthenticationError("Invalid email or password")
        if user.hashed_password is None:
            # SSO-only user — cannot use email/password login
            raise AuthenticationError(
                "This account uses SSO. Please sign in with Microsoft."
            )
        if not password_hash.verify(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        # The same rule as SSO: an active account with a role, or no session
        return assert_may_sign_in(user, account=email, via="password")

    @staticmethod
    def _hash_password(password: str) -> str:
        return password_hash.hash(password)

    @staticmethod
    def create_access_token(user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        exp = now + timedelta(minutes=settings.access_token_expiration_minutes)
        payload = {
            "sub": str(user_id),
            "exp": exp,
            "iat": now,
        }
        return jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    def decode_access_token(token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            user_id = payload.get("sub")
            if user_id is None:
                raise AuthenticationError("Invalid token: missing subject")
            return uuid.UUID(user_id)
        except jwt.ExpiredSignatureError as err:
            raise AuthenticationError("Token has expired") from err
        except jwt.InvalidTokenError as err:
            raise AuthenticationError("Invalid token") from err

    @staticmethod
    def create_refresh_token() -> str:
        """Generate an opaque refresh token string."""
        return secrets.token_urlsafe(64)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token using SHA-256 for storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def store_refresh_token(self, user_id: uuid.UUID, token: str) -> RefreshToken:
        """Hash and store a refresh token in the database."""
        token_hash = self.hash_token(token)
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.refresh_token_expiration_days
        )
        refresh = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(refresh)
        await self.session.flush()
        return refresh

    async def validate_and_rotate_refresh_token(self, token: str) -> uuid.UUID:
        """Validate a refresh token, revoke it, and return the user_id.

        The user must still be active and hold a role: otherwise every one of
        their refresh tokens is revoked, so a removed role or a disabled
        account ends access by the time the current access token expires.
        The caller is responsible for issuing a new refresh token after this.
        """
        token_hash = self.hash_token(token)
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked.is_(False),
            )
        )
        refresh = result.scalar_one_or_none()

        if refresh is None:
            raise AuthenticationError("Invalid refresh token")

        if refresh.expires_at < datetime.now(UTC):
            refresh.is_revoked = True
            await self.session.flush()
            raise AuthenticationError("Refresh token has expired")

        # Revoke the old token (rotation)
        refresh.is_revoked = True
        await self.session.flush()

        user = await self.user_repo.get_by_id(refresh.user_id)
        if user is None or not may_use_app(user):
            await self.revoke_all_user_tokens(refresh.user_id)
            logger.warning(
                "Session refresh refused: no access (user_id=%s role=%s active=%s)",
                refresh.user_id,
                user.role if user is not None else None,
                user.is_active if user is not None else None,
            )
            raise AuthenticationError(SESSION_ENDED_MESSAGE)

        return refresh.user_id

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> int:
        """Revoke all refresh tokens for a user (logout)."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await self.session.flush()
        return cast("CursorResult[Any]", result).rowcount
