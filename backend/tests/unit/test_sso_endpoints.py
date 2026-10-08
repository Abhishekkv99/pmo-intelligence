"""Unit tests for SSO API endpoints (config, callback)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.v1.auth import REFRESH_COOKIE_NAME, router
from app.dependencies import get_db
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.sso_service import GUEST_MESSAGE, SSOService
from app.utils.entitlements import NO_ACCESS_MESSAGE
from app.utils.exceptions import AppError, AuthenticationError, AuthorizationError

# Minimal FastAPI app for unit testing SSO routes
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
    email: str = "sso@example.com",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.full_name = "SSO User"
    user.is_active = is_active
    user.auth_provider = "microsoft_entra"
    user.branch = "US"
    user.access_level = "branch"
    return user


class TestSSOConfigEndpoint:
    """Tests for GET /api/v1/auth/sso/microsoft/config."""

    async def test_returns_sso_config(self) -> None:
        with (
            patch("app.api.v1.auth.settings") as mock_settings,
            patch("app.services.sso_service.settings") as mock_sso_settings,
        ):
            mock_settings.azure_client_id = "client-id-123"
            mock_settings.azure_tenant_id = "tenant-id-456"
            mock_settings.azure_redirect_uri = (
                "http://localhost:3000/auth/callback/microsoft"
            )
            mock_sso_settings.azure_tenant_id = "tenant-id-456"
            mock_sso_settings.azure_allowed_tenant_ids = ""

            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/auth/sso/microsoft/config")

        assert response.status_code == 200
        data = response.json()
        assert data["client_id"] == "client-id-123"
        assert data["tenant_id"] == "tenant-id-456"
        assert data["authority"] == "tenant-id-456"
        assert data["redirect_uri"] == "http://localhost:3000/auth/callback/microsoft"

    async def test_authority_is_organizations_when_other_tenants_are_allowed(
        self,
    ) -> None:
        with (
            patch("app.api.v1.auth.settings") as mock_settings,
            patch("app.services.sso_service.settings") as mock_sso_settings,
        ):
            mock_settings.azure_client_id = "client-id-123"
            mock_settings.azure_tenant_id = "tenant-id-456"
            mock_settings.azure_redirect_uri = (
                "http://localhost:3000/auth/callback/microsoft"
            )
            mock_sso_settings.azure_tenant_id = "tenant-id-456"
            mock_sso_settings.azure_allowed_tenant_ids = "tenant-id-789"

            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/auth/sso/microsoft/config")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "tenant-id-456"
        assert data["authority"] == "organizations"

    async def test_returns_401_when_sso_not_configured(self) -> None:
        with patch("app.api.v1.auth.settings") as mock_settings:
            mock_settings.azure_client_id = ""
            mock_settings.azure_tenant_id = ""

            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/auth/sso/microsoft/config")

        assert response.status_code == 401


class TestSSOCallbackEndpoint:
    """Tests for POST /api/v1/auth/sso/microsoft/callback."""

    async def test_callback_returns_tokens_and_sets_cookie(self) -> None:
        mock_user = _make_mock_user()

        with (
            patch.object(SSOService, "authenticate_sso", return_value=mock_user),
            patch.object(
                AuthService,
                "create_access_token",
                return_value="app.access.token",
            ),
            patch.object(
                AuthService,
                "create_refresh_token",
                return_value="raw-refresh",
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
                        "/api/v1/auth/sso/microsoft/callback",
                        json={
                            "code": "auth-code-from-microsoft",
                            "code_verifier": "a" * 43,
                            "redirect_uri": "http://localhost:3000/auth/callback/microsoft",
                        },
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "app.access.token"
        assert data["token_type"] == "bearer"
        assert REFRESH_COOKIE_NAME in response.cookies

    async def test_callback_sso_failure_returns_401(self) -> None:
        with patch.object(
            SSOService,
            "authenticate_sso",
            side_effect=AuthenticationError("SSO token exchange failed"),
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/sso/microsoft/callback",
                        json={
                            "code": "bad-code",
                            "code_verifier": "v" * 43,
                            "redirect_uri": "http://localhost:3000/callback",
                        },
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 401

    @pytest.mark.parametrize("message", [NO_ACCESS_MESSAGE, GUEST_MESSAGE])
    async def test_callback_refused_sign_in_returns_403_with_the_reason(
        self, message: str
    ) -> None:
        """The callback page shows this detail, so it must reach the client."""
        with patch.object(
            SSOService, "authenticate_sso", side_effect=AuthorizationError(message)
        ):
            _app.dependency_overrides[get_db] = _mock_db_override
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=_app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/v1/auth/sso/microsoft/callback",
                        json={
                            "code": "code",
                            "code_verifier": "v" * 43,
                            "redirect_uri": "http://localhost:3000/callback",
                        },
                    )
            finally:
                _app.dependency_overrides.clear()

        assert response.status_code == 403
        assert response.json() == {"detail": message}
        assert "set-cookie" not in response.headers

    async def test_callback_validates_code_verifier_length(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/auth/sso/microsoft/callback",
                    json={
                        "code": "code",
                        "code_verifier": "short",
                        "redirect_uri": "http://localhost:3000/callback",
                    },
                )
        finally:
            _app.dependency_overrides.clear()

        assert response.status_code == 422

    async def test_callback_validates_required_fields(self) -> None:
        _app.dependency_overrides[get_db] = _mock_db_override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/v1/auth/sso/microsoft/callback",
                    json={},
                )
        finally:
            _app.dependency_overrides.clear()

        assert response.status_code == 422
