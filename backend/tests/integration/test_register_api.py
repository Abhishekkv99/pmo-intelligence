"""The register routes against a real database.

Editing is for PMO managers and admins; a single placement is read under
placement scope. Uniqueness, dates and the people rule (named users must be
active and hold a role) are enforced by the service, so they hold for the
admin pages and the CSV import alike.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.models.enums import Role
from app.models.user import User
from app.services.auth_service import AuthService

pytestmark = pytest.mark.asyncio


async def _user(db: AsyncSession, name: str, role: Role | None) -> User:
    return await UserRepository(db).create(
        email=f"{name}@example.com",
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=name.title(),
        role=role.value if role else None,
    )


async def _post(client: AsyncClient, path: str, body: dict[str, Any]) -> Any:
    response = await client.post(f"/api/v1{path}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _world(client: AsyncClient, db: AsyncSession) -> dict[str, Any]:
    ps = await _user(db, "pat", Role.PS)
    lead = await _user(db, "tia", Role.TECH_LEAD)
    client_row = await _post(client, "/clients", {"name": "Barclays"})
    consultant = await _post(
        client, "/consultants", {"full_name": "Vibin Cholayil", "email": "V@x.com"}
    )
    project = await _post(
        client,
        "/projects",
        {
            "client_id": client_row["id"],
            "name": "Payments",
            "tech_lead_user_id": str(lead.id),
        },
    )
    placement = await _post(
        client,
        "/placements",
        {
            "consultant_id": consultant["id"],
            "project_id": project["id"],
            "start_date": "2026-08-17",
            "expected_end_date": "2027-02-17",
            "ps_user_id": str(ps.id),
        },
    )
    return {
        "ps": ps,
        "lead": lead,
        "client": client_row,
        "consultant": consultant,
        "project": project,
        "placement": placement,
    }


class TestCreateAndList:
    async def test_manager_builds_a_placement(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)

        placement = w["placement"]
        assert placement["consultant"]["full_name"] == "Vibin Cholayil"
        assert placement["consultant"]["email"] == "v@x.com"
        assert placement["client"]["name"] == "Barclays"
        assert placement["project"]["name"] == "Payments"
        assert placement["ps"]["email"] == "pat@example.com"
        assert placement["tech_lead"]["email"] == "tia@example.com"
        assert placement["sme"] is None
        assert placement["extension_status"] == "not_due"
        assert placement["status"] == "active"

        listed = (await manager_client.get("/api/v1/placements")).json()
        assert [p["id"] for p in listed] == [placement["id"]]
        projects = (await manager_client.get("/api/v1/projects")).json()
        assert projects[0]["client_name"] == "Barclays"
        assert projects[0]["tech_lead"]["full_name"] == "Tia"

    async def test_names_are_tidied(self, manager_client: AsyncClient) -> None:
        body = await _post(manager_client, "/clients", {"name": "  Capital   One "})

        assert body["name"] == "Capital One"


class TestUniqueness:
    async def test_client_name_is_unique_ignoring_case_and_spacing(
        self, manager_client: AsyncClient
    ) -> None:
        await _post(manager_client, "/clients", {"name": "Capital One"})

        response = await manager_client.post(
            "/api/v1/clients", json={"name": "capital  ONE"}
        )

        assert response.status_code == 409

    async def test_consultant_email_is_unique_ignoring_case(
        self, manager_client: AsyncClient
    ) -> None:
        await _post(
            manager_client, "/consultants", {"full_name": "A", "email": "a@x.com"}
        )

        response = await manager_client.post(
            "/api/v1/consultants", json={"full_name": "B", "email": "A@X.com"}
        )

        assert response.status_code == 409

    async def test_project_name_is_unique_per_client(
        self, manager_client: AsyncClient
    ) -> None:
        one = await _post(manager_client, "/clients", {"name": "One"})
        two = await _post(manager_client, "/clients", {"name": "Two"})
        await _post(manager_client, "/projects", {"client_id": one["id"], "name": "P"})

        same = await manager_client.post(
            "/api/v1/projects", json={"client_id": one["id"], "name": " p "}
        )
        other_client = await manager_client.post(
            "/api/v1/projects", json={"client_id": two["id"], "name": "P"}
        )

        assert same.status_code == 409
        assert other_client.status_code == 201

    async def test_same_placement_twice_is_refused(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)

        response = await manager_client.post(
            "/api/v1/placements",
            json={
                "consultant_id": w["consultant"]["id"],
                "project_id": w["project"]["id"],
                "start_date": "2026-08-17",
            },
        )

        assert response.status_code == 409


class TestValidation:
    async def test_end_before_start_is_refused(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)

        response = await manager_client.patch(
            f"/api/v1/placements/{w['placement']['id']}",
            json={"expected_end_date": "2026-01-01"},
        )

        assert response.status_code == 422
        assert "before start_date" in response.json()["detail"]

    @pytest.mark.parametrize("role", [None, Role.SME])
    async def test_named_people_must_be_active_with_a_role(
        self,
        manager_client: AsyncClient,
        db_session: AsyncSession,
        role: Role | None,
    ) -> None:
        w = await _world(manager_client, db_session)
        person = await _user(db_session, "nobody", role)
        if role is not None:
            person.is_active = False
            await db_session.flush()

        response = await manager_client.patch(
            f"/api/v1/placements/{w['placement']['id']}",
            json={"sme_user_id": str(person.id)},
        )

        assert response.status_code == 422
        assert "sme_user_id" in response.json()["detail"]

    async def test_unknown_reference_is_422(self, manager_client: AsyncClient) -> None:
        response = await manager_client.post(
            "/api/v1/projects", json={"client_id": str(uuid.uuid4()), "name": "P"}
        )

        assert response.status_code == 422

    async def test_required_field_cannot_be_cleared(
        self, manager_client: AsyncClient
    ) -> None:
        client = await _post(manager_client, "/clients", {"name": "One"})

        response = await manager_client.patch(
            f"/api/v1/clients/{client['id']}", json={"name": None}
        )

        assert response.status_code == 422


class TestPartialUpdate:
    async def test_only_sent_fields_change_and_null_clears(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)
        path = f"/api/v1/placements/{w['placement']['id']}"

        response = await manager_client.patch(
            path, json={"extension_status": "requested", "ps_user_id": None}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["extension_status"] == "requested"
        assert body["ps"] is None
        assert body["expected_end_date"] == "2027-02-17"

    async def test_ending_a_placement(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)

        response = await manager_client.patch(
            f"/api/v1/placements/{w['placement']['id']}",
            json={"status": "terminated", "ended_reason": "Client cut the budget"},
        )

        assert response.json()["status"] == "terminated"
        assert response.json()["ended_reason"] == "Client cut the budget"


class TestEditOtherRecords:
    @pytest.mark.parametrize(
        ("resource", "body", "field"),
        [
            ("consultant", {"phone": "07700 900123"}, "phone"),
            ("client", {"industry": "Banking"}, "industry"),
            ("project", {"client_manager_name": "Dana Lee"}, "client_manager_name"),
        ],
    )
    async def test_an_edit_answers_the_saved_record(
        self,
        manager_client: AsyncClient,
        db_session: AsyncSession,
        resource: str,
        body: dict[str, Any],
        field: str,
    ) -> None:
        w = await _world(manager_client, db_session)
        record = w[resource]

        response = await manager_client.patch(
            f"/api/v1/{resource}s/{record['id']}", json=body
        )

        assert response.status_code == 200, response.text
        assert response.json()[field] == body[field]
        assert response.json()["updated_at"]


class TestAccess:
    async def test_scoped_user_reads_their_placement_only(
        self,
        manager_client: AsyncClient,
        authenticated_client: AsyncClient,
        test_user: User,
        db_session: AsyncSession,
    ) -> None:
        w = await _world(manager_client, db_session)
        mine = await _post(
            manager_client,
            "/placements",
            {
                "consultant_id": w["consultant"]["id"],
                "project_id": w["project"]["id"],
                "start_date": "2027-03-01",
                "ps_user_id": str(test_user.id),
            },
        )

        own = await authenticated_client.get(f"/api/v1/placements/{mine['id']}")
        other = await authenticated_client.get(
            f"/api/v1/placements/{w['placement']['id']}"
        )

        assert own.status_code == 200
        assert other.status_code == 404

    async def test_an_sme_reads_their_placement_without_the_contract_fields(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        w = await _world(manager_client, db_session)
        sme = await _user(db_session, "sam", Role.SME)
        placement_id = w["placement"]["id"]
        await manager_client.patch(
            f"/api/v1/placements/{placement_id}",
            json={
                "sme_user_id": str(sme.id),
                "extension_status": "requested",
                "rate_band": "B",
            },
        )

        def bearer(user: User) -> dict[str, str]:
            token = AuthService.create_access_token(user.id)
            return {"Authorization": f"Bearer {token}"}

        as_sme = await manager_client.get(
            f"/api/v1/placements/{placement_id}", headers=bearer(sme)
        )
        as_ps = await manager_client.get(
            f"/api/v1/placements/{placement_id}", headers=bearer(w["ps"])
        )

        assert as_sme.status_code == 200
        body = as_sme.json()
        assert body["extension_status"] is None
        assert body["rate_band"] is None
        assert body["ended_reason"] is None
        assert body["start_date"] == "2026-08-17"
        assert body["sme"]["full_name"] == "Sam"
        assert as_ps.json()["extension_status"] == "requested"
        assert as_ps.json()["rate_band"] == "B"

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/v1/placements"),
            ("get", "/api/v1/consultants"),
            ("get", "/api/v1/users"),
            ("post", "/api/v1/clients"),
        ],
    )
    async def test_scoped_roles_cannot_edit_or_list(
        self, authenticated_client: AsyncClient, method: str, path: str
    ) -> None:
        response = await getattr(authenticated_client, method)(path)

        assert response.status_code == 403

    async def test_scoped_user_cannot_edit_their_own_placement(
        self,
        manager_client: AsyncClient,
        authenticated_client: AsyncClient,
        test_user: User,
        db_session: AsyncSession,
    ) -> None:
        w = await _world(manager_client, db_session)
        await manager_client.patch(
            f"/api/v1/placements/{w['placement']['id']}",
            json={"ps_user_id": str(test_user.id)},
        )

        response = await authenticated_client.patch(
            f"/api/v1/placements/{w['placement']['id']}",
            json={"extension_status": "confirmed"},
        )

        assert response.status_code == 403


class TestUserList:
    async def test_lists_users_without_secrets(
        self, manager_client: AsyncClient, test_manager: User
    ) -> None:
        body = (await manager_client.get("/api/v1/users")).json()

        assert body == [
            {
                "id": str(test_manager.id),
                "email": "manager@example.com",
                "full_name": "Manager User",
                "role": "pmo_manager",
                "is_active": True,
                "signed_in_with_microsoft": False,
            }
        ]
