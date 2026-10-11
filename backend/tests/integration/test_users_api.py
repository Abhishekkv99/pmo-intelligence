"""The Users and roles routes against a real database.

Granting a role creates the user by email; removing one ends their
sessions; the last active PMO manager keeps the role, from the page and from
the CLI alike (one rule in ``UserRoleService``).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.models.enums import Role
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.user_roles import RoleChangeRefusedError, UserRoleService

pytestmark = pytest.mark.asyncio


async def _user(
    db: AsyncSession, name: str, role: Role | None, *, active: bool = True
) -> User:
    user = await UserRepository(db).create(
        email=f"{name}@example.com",
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=name.title(),
        role=role.value if role else None,
    )
    user.is_active = active
    await db.flush()
    return user


class TestGrant:
    async def test_granting_creates_a_user_by_email(
        self, manager_client: AsyncClient
    ) -> None:
        response = await manager_client.post(
            "/api/v1/users", json={"email": "New.Person@Example.com", "role": "sme"}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["user"]["email"] == "new.person@example.com"
        assert body["user"]["role"] == "sme"
        assert body["user"]["signed_in_with_microsoft"] is False
        assert "created with role sme" in body["message"]

    async def test_granting_an_existing_user_changes_the_role(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _user(db_session, "pat", Role.PS)

        response = await manager_client.post(
            "/api/v1/users", json={"email": "pat@example.com", "role": "cdm"}
        )

        assert response.json()["user"]["role"] == "cdm"
        assert response.json()["message"] == "pat@example.com: role ps -> cdm"

    async def test_not_an_email_is_422(self, manager_client: AsyncClient) -> None:
        response = await manager_client.post(
            "/api/v1/users", json={"email": "not-an-email", "role": "sme"}
        )

        assert response.status_code == 422


class TestChange:
    async def test_removing_a_role_ends_the_sessions(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        pat = await _user(db_session, "pat", Role.PS)
        await AuthService(db_session).store_refresh_token(pat.id, "refresh-1")

        response = await manager_client.patch(
            f"/api/v1/users/{pat.id}", json={"role": None}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["user"]["role"] is None
        assert "1 session(s) ended" in body["message"]

    async def test_unknown_user_is_404(self, manager_client: AsyncClient) -> None:
        response = await manager_client.patch(
            f"/api/v1/users/{uuid.uuid4()}", json={"role": "sme"}
        )

        assert response.status_code == 404


class TestLastManager:
    async def test_the_last_manager_keeps_the_role(
        self, manager_client: AsyncClient, test_manager: User
    ) -> None:
        response = await manager_client.patch(
            f"/api/v1/users/{test_manager.id}", json={"role": "admin"}
        )

        assert response.status_code == 409
        assert "last active PMO manager" in response.json()["detail"]

    async def test_a_disabled_manager_does_not_count(
        self,
        manager_client: AsyncClient,
        test_manager: User,
        db_session: AsyncSession,
    ) -> None:
        await _user(db_session, "gone", Role.PMO_MANAGER, active=False)

        response = await manager_client.patch(
            f"/api/v1/users/{test_manager.id}", json={"role": None}
        )

        assert response.status_code == 409

    async def test_handing_over_then_stepping_down(
        self,
        manager_client: AsyncClient,
        test_manager: User,
        db_session: AsyncSession,
    ) -> None:
        await _user(db_session, "next", Role.ADMIN)
        await manager_client.post(
            "/api/v1/users", json={"email": "next@example.com", "role": "pmo_manager"}
        )

        response = await manager_client.patch(
            f"/api/v1/users/{test_manager.id}", json={"role": "admin"}
        )

        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"

    async def test_the_cli_service_refuses_too(
        self, test_manager: User, db_session: AsyncSession
    ) -> None:
        with pytest.raises(RoleChangeRefusedError, match="last active PMO manager"):
            await UserRoleService(db_session).set_role(test_manager.email, None)


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "/api/v1/users", {"email": "x@example.com", "role": "sme"}),
            ("patch", f"/api/v1/users/{uuid.uuid4()}", {"role": "sme"}),
        ],
    )
    async def test_scoped_roles_cannot_change_roles(
        self,
        authenticated_client: AsyncClient,
        method: str,
        path: str,
        body: dict[str, str],
    ) -> None:
        response = await getattr(authenticated_client, method)(path, json=body)

        assert response.status_code == 403
