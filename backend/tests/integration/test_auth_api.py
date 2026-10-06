"""Integration tests for authentication API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService


class TestRegister:
    """Tests for POST /api/v1/auth/register."""

    async def test_register_creates_user(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "full_name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()

        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert data["is_active"] is True
        # A new account has no role until one is granted.
        assert data["role"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_register_bootstrap_admin_gets_the_manager_role(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "Boss@Example.com")
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "boss@example.com",
                "password": "SecurePass123",
                "full_name": "Boss",
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "pmo_manager"

    async def test_register_duplicate_email_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Pre-create a user
        repo = UserRepository(db_session)
        await repo.create(
            email="taken@example.com",
            hashed_password=AuthService._hash_password("SomePass123"),
            full_name="Existing User",
        )

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "taken@example.com",
                "password": "AnotherPass123",
                "full_name": "Another User",
            },
        )
        assert response.status_code == 401
        assert "already registered" in response.json()["detail"]

    async def test_register_short_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@example.com",
                "password": "short",
                "full_name": "Short Pass User",
            },
        )
        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    async def test_login_returns_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Create a user first
        repo = UserRepository(db_session)
        await repo.create(
            email="loginuser@example.com",
            hashed_password=AuthService._hash_password("LoginPass123"),
            full_name="Login User",
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "loginuser@example.com",
                "password": "LoginPass123",
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        repo = UserRepository(db_session)
        await repo.create(
            email="wrongpass@example.com",
            hashed_password=AuthService._hash_password("CorrectPass"),
            full_name="Wrong Pass User",
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "wrongpass@example.com",
                "password": "WrongPass",
            },
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    async def test_login_nonexistent_user_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "AnyPass123",
            },
        )
        assert response.status_code == 401


class TestMe:
    """Tests for GET /api/v1/auth/me."""

    async def test_me_returns_current_user(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()

        assert data["email"] == "testuser@example.com"
        assert data["full_name"] == "Test User"
        assert data["is_active"] is True
        # The fixture creates a placement specialist.
        assert data["role"] == "ps"

    async def test_me_without_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestProtectedEndpoints:
    """Tests that protected endpoints return 401 without auth."""

    async def test_processing_status_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/processing/status")
        assert response.status_code == 401
