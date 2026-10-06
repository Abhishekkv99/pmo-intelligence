"""Unit tests for auth API endpoints (login, refresh, logout)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.v1.auth import REFRESH_COOKIE_NAME, router
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.services.auth_service import AuthService
from app.utils.exceptions import AppError, AuthenticationError

# Minimal FastAPI app for unit testing auth routes (no middleware, no other routers)
_app = FastAPI()
_app.include_router(router, prefix="/api/v1/auth")


@_app.exception_handler(AppError)
async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


def _mock_db_override() -> AsyncMock:
    return AsyncMock()


def _make_mock_user(
    user_id: uuid.UUID | None = None,
    email: str = "test@example.com",
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.full_name = "Test User"
    user.is_active = True
    user.auth_provider = "local"
    # A real value, not a spec-mock child: UserResponse validates the role
    # as an enum, and a MagicMock attribute is rejected by Pydantic.
    user.role = None
    user.created_at = datetime.now(UTC)
    return user


class TestLocalAuthDisabled:
    """When the deployment is SSO-only, password sign-in must be refused.

    Removing the form from the UI is presentation only — these endpoints stay
    reachable to anyone with the URL, so the check has to live here.
    """

    async def test_login_returns_403_when_local_auth_disabled(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            with patch("app.api.v1.auth.settings") as mock_settings:
                mock_settings.local_auth_enabled = False
                async with AsyncClient(
                    transport=ASGITransport(app=_app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/login",
                        json={"email": "a@b.com", "password": "secret123"},
                    )
            assert response.status_code == 403
            assert "Microsoft" in response.json()["detail"]
        finally:
            _app.dependency_overrides.clear()

    async def test_register_returns_403_when_local_auth_disabled(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            with patch("app.api.v1.auth.settings") as mock_settings:
                mock_settings.local_auth_enabled = False
                async with AsyncClient(
                    transport=ASGITransport(app=_app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/register",
                        json={
                            "email": "a@b.com",
                            "password": "secret123",
                            "full_name": "A B",
                        },
                    )
            assert response.status_code == 403
        finally:
            _app.dependency_overrides.clear()

    async def test_login_is_refused_before_credentials_are_checked(self) -> None:
        """The gate must short-circuit, not merely reject a bad password."""
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            with (
                patch("app.api.v1.auth.settings") as mock_settings,
                patch("app.api.v1.auth.AuthService") as mock_service_cls,
            ):
                mock_settings.local_auth_enabled = False
                async with AsyncClient(
                    transport=ASGITransport(app=_app), base_url="http://test"
                ) as client:
                    await client.post(
                        "/api/v1/auth/login",
                        json={"email": "a@b.com", "password": "secret123"},
                    )
            mock_service_cls.assert_not_called()
        finally:
            _app.dependency_overrides.clear()

    async def test_sso_callback_is_unaffected_by_the_gate(self) -> None:
        """Microsoft sign-in must keep working — it is the only way in."""
        mock_user = _make_mock_user()
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            with (
                patch("app.api.v1.auth.settings") as mock_settings,
                patch("app.api.v1.auth.SSOService") as mock_sso_cls,
                patch.object(AuthService, "create_access_token", return_value="tok"),
                patch.object(AuthService, "create_refresh_token", return_value="raw"),
                patch.object(AuthService, "store_refresh_token", new=AsyncMock()),
            ):
                mock_settings.local_auth_enabled = False
                mock_settings.cookie_secure = False
                mock_settings.cookie_domain = ""
                mock_sso_cls.return_value.authenticate_sso = AsyncMock(
                    return_value=mock_user
                )
                async with AsyncClient(
                    transport=ASGITransport(app=_app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/sso/microsoft/callback",
                        json={
                            "code": "abc",
                            "code_verifier": "v" * 43,
                            "redirect_uri": "http://localhost:3000/cb",
                        },
                    )
            assert response.status_code != 403
        finally:
            _app.dependency_overrides.clear()


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login."""

    async def test_login_returns_access_token_and_sets_cookie(self) -> None:
        mock_user = _make_mock_user()

        with (
            patch.object(AuthService, "authenticate", return_value=mock_user),
            patch.object(
                AuthService,
                "create_access_token",
                return_value="access.jwt.token",
            ),
            patch.object(
                AuthService,
                "create_refresh_token",
                return_value="raw-refresh-token",
            ),
            patch.object(AuthService, "store_refresh_token", return_value=MagicMock()),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/login",
                        json={
                            "email": "test@example.com",
                            "password": "password123",
                        },
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "access.jwt.token"
        assert data["token_type"] == "bearer"

        # Verify refresh token cookie is set
        cookies = response.cookies
        assert REFRESH_COOKIE_NAME in cookies

    async def test_login_invalid_credentials_returns_401(self) -> None:
        with patch.object(
            AuthService,
            "authenticate",
            side_effect=AuthenticationError("Invalid email or password"),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/login",
                        json={
                            "email": "bad@example.com",
                            "password": "wrong",
                        },
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 401


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh."""

    async def test_refresh_rotates_token_and_returns_new_access(self) -> None:
        user_id = uuid.uuid4()

        with (
            patch.object(
                AuthService,
                "validate_and_rotate_refresh_token",
                return_value=user_id,
            ),
            patch.object(
                AuthService,
                "create_access_token",
                return_value="new.access.token",
            ),
            patch.object(
                AuthService,
                "create_refresh_token",
                return_value="new-refresh-token",
            ),
            patch.object(AuthService, "store_refresh_token", return_value=MagicMock()),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/refresh",
                        cookies={REFRESH_COOKIE_NAME: "old-refresh-token"},
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new.access.token"
        assert data["token_type"] == "bearer"

        # New refresh cookie should be set
        cookies = response.cookies
        assert REFRESH_COOKIE_NAME in cookies

    async def test_refresh_without_cookie_returns_401(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/auth/refresh")
        finally:
            _app.dependency_overrides.clear()

        assert response.status_code == 401

    async def test_refresh_with_invalid_token_returns_401(self) -> None:
        with patch.object(
            AuthService,
            "validate_and_rotate_refresh_token",
            side_effect=AuthenticationError("Invalid refresh token"),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/refresh",
                        cookies={REFRESH_COOKIE_NAME: "bad-token"},
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 401
        # Verify stale cookie is cleared to prevent redirect loops
        cookie_header = response.headers.get("set-cookie", "")
        assert "refresh_token" in cookie_header
        assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header

    async def test_refresh_with_expired_token_returns_401(self) -> None:
        with patch.object(
            AuthService,
            "validate_and_rotate_refresh_token",
            side_effect=AuthenticationError("Refresh token has expired"),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/refresh",
                        cookies={REFRESH_COOKIE_NAME: "expired-token"},
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 401


class TestLogoutEndpoint:
    """Tests for POST /api/v1/auth/logout."""

    async def test_logout_revokes_tokens_and_clears_cookie(self) -> None:
        mock_user = _make_mock_user()

        with patch.object(AuthService, "revoke_all_user_tokens", return_value=2):

            async def _override_user() -> User:
                return mock_user

            _app.dependency_overrides[get_db] = _mock_db_override
            _app.dependency_overrides[get_current_user] = _override_user
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                    headers={"Authorization": "Bearer fake.jwt.token"},
                ) as client:
                    response = await client.post("/api/v1/auth/logout")
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"
        assert data["revoked_tokens"] == 2

        # Cookie should be cleared (max-age=0 or deleted)
        set_cookie_header = response.headers.get("set-cookie", "")
        assert REFRESH_COOKIE_NAME in set_cookie_header

    async def test_logout_without_auth_returns_401(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/auth/logout")
        finally:
            _app.dependency_overrides.clear()

        assert response.status_code == 401

    async def test_logout_with_zero_tokens(self) -> None:
        mock_user = _make_mock_user()

        with patch.object(AuthService, "revoke_all_user_tokens", return_value=0):

            async def _override_user() -> User:
                return mock_user

            _app.dependency_overrides[get_db] = _mock_db_override
            _app.dependency_overrides[get_current_user] = _override_user
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                    headers={"Authorization": "Bearer fake.jwt.token"},
                ) as client:
                    response = await client.post("/api/v1/auth/logout")
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["revoked_tokens"] == 0


class TestMeEndpoint:
    """Tests for GET /api/v1/auth/me — the profile carries the entitlement."""

    async def _get_me(self, mock_user: MagicMock) -> dict[str, object]:
        async def _override_user() -> User:
            return mock_user

        _app.dependency_overrides[get_db] = _mock_db_override
        _app.dependency_overrides[get_current_user] = _override_user
        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
                headers={"Authorization": "Bearer fake.jwt.token"},
            ) as client:
                response = await client.get("/api/v1/auth/me")
        finally:
            _app.dependency_overrides.clear()

        assert response.status_code == 200
        return response.json()

    async def test_me_returns_the_role(self) -> None:
        mock_user = _make_mock_user(email="manager@example.com")
        mock_user.role = "pmo_manager"

        data = await self._get_me(mock_user)

        assert data["role"] == "pmo_manager"
        assert "branch" not in data
        assert "access_level" not in data

    async def test_me_reports_no_role_as_null(self) -> None:
        data = await self._get_me(_make_mock_user())

        assert data["role"] is None
