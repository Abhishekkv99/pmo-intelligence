"""Tests for security headers middleware."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def sec_client() -> AsyncGenerator[AsyncClient]:
    """App client for security header testing."""
    test_app = create_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSecurityHeaders:
    """Test security headers are present on responses."""

    async def test_x_content_type_options(self, sec_client: AsyncClient) -> None:
        """Response should include X-Content-Type-Options: nosniff."""
        response = await sec_client.get("/api/v1/health")
        assert response.headers["x-content-type-options"] == "nosniff"

    async def test_x_frame_options(self, sec_client: AsyncClient) -> None:
        """Response should include X-Frame-Options: DENY."""
        response = await sec_client.get("/api/v1/health")
        assert response.headers["x-frame-options"] == "DENY"

    async def test_x_xss_protection(self, sec_client: AsyncClient) -> None:
        """Response should disable legacy XSS filter."""
        response = await sec_client.get("/api/v1/health")
        assert response.headers["x-xss-protection"] == "0"

    async def test_referrer_policy(self, sec_client: AsyncClient) -> None:
        """Response should include Referrer-Policy."""
        response = await sec_client.get("/api/v1/health")
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    async def test_permissions_policy(self, sec_client: AsyncClient) -> None:
        """Response should restrict browser permissions."""
        response = await sec_client.get("/api/v1/health")
        assert "camera=()" in response.headers["permissions-policy"]
        assert "microphone=()" in response.headers["permissions-policy"]
        assert "geolocation=()" in response.headers["permissions-policy"]

    async def test_headers_on_error_responses(self, sec_client: AsyncClient) -> None:
        """Security headers should be present even on error responses."""
        response = await sec_client.get("/api/v1/auth/me")
        # 401 because no auth token
        assert response.status_code == 401
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


class TestCorsLockdown:
    """Test CORS is locked down to specific methods and headers."""

    async def test_cors_allows_configured_origin(self, sec_client: AsyncClient) -> None:
        """CORS should allow requests from configured origins."""
        response = await sec_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )

    async def test_cors_rejects_unknown_origin(self, sec_client: AsyncClient) -> None:
        """CORS should not allow requests from unknown origins."""
        response = await sec_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in response.headers

    async def test_cors_allows_get_method(self, sec_client: AsyncClient) -> None:
        """CORS should allow GET method."""
        response = await sec_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        assert "GET" in allowed

    async def test_cors_allows_post_method(self, sec_client: AsyncClient) -> None:
        """CORS should allow POST method."""
        response = await sec_client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        assert "POST" in allowed
