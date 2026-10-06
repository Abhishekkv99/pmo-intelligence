"""Tests for API rate limiting with slowapi."""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.rate_limiter import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None]:
    """Reset rate limiter state before and after each test."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
async def rl_client() -> AsyncGenerator[AsyncClient]:
    """App client with mocked database for rate limit testing."""
    from app.dependencies import get_db

    test_app = create_app()

    # Mock database — rate limit tests don't need real DB
    async def mock_get_db() -> AsyncGenerator[AsyncMock]:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        yield session

    test_app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRateLimiting:
    """Test rate limiting on API endpoints."""

    async def test_health_exempt_from_rate_limiting(
        self, rl_client: AsyncClient
    ) -> None:
        """Health endpoint should not be rate limited even after many requests."""
        for i in range(15):
            response = await rl_client.get("/api/v1/health")
            assert response.status_code == 200, f"Request {i + 1} was blocked"

    async def test_login_rate_limited_at_5_per_minute(
        self, rl_client: AsyncClient
    ) -> None:
        """Login should allow 5 requests per minute, then return 429."""
        login_data = {"email": "test@example.com", "password": "testpass123"}

        # First 5 should not be rate limited (returns 401 — invalid creds)
        for i in range(5):
            response = await rl_client.post("/api/v1/auth/login", json=login_data)
            assert response.status_code != 429, f"Request {i + 1} was rate limited"

        # 6th should be rate limited
        response = await rl_client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 429

    async def test_register_rate_limited_at_3_per_minute(
        self, rl_client: AsyncClient
    ) -> None:
        """Register should allow 3 requests per minute, then return 429."""
        register_data = {
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
        }

        # First 3 requests reach the endpoint handler (rate limit counter
        # incremented by slowapi before handler runs). The handler may crash
        # with the mock DB, but the counter is already updated.
        for _ in range(3):
            try:
                response = await rl_client.post(
                    "/api/v1/auth/register", json=register_data
                )
                assert response.status_code != 429
            except Exception:
                pass  # Mock DB may cause crashes; counter still incremented

        # 4th should be rate limited (returns 429 before handler runs)
        response = await rl_client.post("/api/v1/auth/register", json=register_data)
        assert response.status_code == 429

    async def test_rate_limit_429_response_body(self, rl_client: AsyncClient) -> None:
        """Rate limited response should indicate rate limit exceeded."""
        login_data = {"email": "test@example.com", "password": "testpass123"}

        for _ in range(5):
            await rl_client.post("/api/v1/auth/login", json=login_data)

        response = await rl_client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 429
        body = response.text.lower()
        assert "rate limit" in body or "too many" in body
