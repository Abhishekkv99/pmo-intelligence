"""Unit tests for authentication Pydantic schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse


class TestUserRegister:
    """Tests for UserRegister schema validation."""

    def test_valid_register_data(self) -> None:
        data = UserRegister(
            email="user@example.com",
            password="securePass1",
            full_name="Test User",
        )
        assert data.email == "user@example.com"
        assert data.password == "securePass1"
        assert data.full_name == "Test User"

    def test_rejects_short_password(self) -> None:
        with pytest.raises(ValidationError, match="at least 8"):
            UserRegister(
                email="user@example.com",
                password="short",
                full_name="Test User",
            )

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            UserRegister(
                email="not-an-email",
                password="securePass1",
                full_name="Test User",
            )

    def test_rejects_empty_full_name(self) -> None:
        with pytest.raises(ValidationError):
            UserRegister(
                email="user@example.com",
                password="securePass1",
                full_name="",
            )


class TestUserLogin:
    """Tests for UserLogin schema validation."""

    def test_valid_login_data(self) -> None:
        data = UserLogin(
            email="user@example.com",
            password="securePass1",
        )
        assert data.email == "user@example.com"
        assert data.password == "securePass1"


class TestTokenResponse:
    """Tests for TokenResponse schema."""

    def test_token_response_defaults(self) -> None:
        response = TokenResponse(access_token="jwt.token.here")
        assert response.access_token == "jwt.token.here"
        assert response.token_type == "bearer"


class TestUserResponse:
    """Tests for UserResponse schema with from_attributes."""

    def test_user_response_from_dict(self) -> None:
        now = datetime.now(UTC)
        response = UserResponse(
            id=uuid.uuid4(),
            email="user@example.com",
            full_name="Test User",
            is_active=True,
            role="ps",
            created_at=now,
        )
        assert response.email == "user@example.com"
        assert response.is_active is True
        assert response.role == "ps"

    def test_user_response_serialises_the_role_as_a_plain_string(self) -> None:
        response = UserResponse(
            id=uuid.uuid4(),
            email="manager@example.com",
            full_name="Manager",
            is_active=True,
            role="pmo_manager",
            created_at=datetime.now(UTC),
        )
        dumped = response.model_dump(mode="json")
        assert dumped["role"] == "pmo_manager"

    def test_user_response_accepts_no_role(self) -> None:
        response = UserResponse(
            id=uuid.uuid4(),
            email="new@example.com",
            full_name="New User",
            is_active=True,
            role=None,
            created_at=datetime.now(UTC),
        )
        assert response.model_dump(mode="json")["role"] is None

    def test_user_response_requires_the_role_field(self) -> None:
        # Required (though nullable), never defaulted: a response built
        # without the entitlement must fail loudly rather than read as one.
        with pytest.raises(ValidationError):
            UserResponse(
                id=uuid.uuid4(),
                email="user@example.com",
                full_name="Test User",
                is_active=True,
                created_at=datetime.now(UTC),
            )

    def test_user_response_rejects_an_unknown_role(self) -> None:
        base = {
            "id": uuid.uuid4(),
            "email": "user@example.com",
            "full_name": "Test User",
            "is_active": True,
            "created_at": datetime.now(UTC),
        }
        with pytest.raises(ValidationError):
            UserResponse(**base, role="superuser")
