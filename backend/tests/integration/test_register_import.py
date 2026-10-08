"""The register CSV import against a real database, through the route.

Pinned here: a dry run writes nothing; a Confirm writes every row or none;
a re-import of the same sheet changes nothing; a filled cell overwrites and
an empty one keeps the stored value; people are existing users with a role.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.models.enums import Role
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.register_import import COLUMNS

pytestmark = pytest.mark.asyncio

PATH = "/api/v1/register/import"


def _row(**values: str) -> str:
    base = {
        "consultant_full_name": "Vibin Cholayil",
        "consultant_email": "vibin@example.com",
        "client_name": "Barclays",
        "project_name": "Payments",
        "start_date": "17/08/2026",
        "expected_end_date": "2027-02-17",
    }
    base.update(values)
    return ",".join(base.get(column, "") for column in COLUMNS)


def _csv(*rows: str) -> bytes:
    return ("\r\n".join([",".join(COLUMNS), *rows]) + "\r\n").encode()


async def _import(
    client: AsyncClient, content: bytes, *, dry_run: bool
) -> dict[str, Any]:
    response = await client.post(
        PATH,
        params={"dry_run": str(dry_run).lower()},
        files={"file": ("register.csv", content, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _user(db: AsyncSession, name: str, role: Role | None) -> User:
    return await UserRepository(db).create(
        email=f"{name}@example.com",
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=name.title(),
        role=role.value if role else None,
    )


class TestDryRunAndConfirm:
    async def test_dry_run_previews_and_writes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        body = await _import(manager_client, _csv(_row()), dry_run=True)

        assert body["dry_run"] is True
        assert body["applied"] is False
        assert body["summary"] == {
            "rows": 1,
            "created": 1,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
        }
        row = body["rows"][0]
        assert row["row"] == 2
        assert row["outcome"] == "create"
        assert row["changes"] == [
            "client Barclays: created",
            "consultant Vibin Cholayil: created",
            "project Barclays / Payments: created",
            "placement from 2026-08-17: created",
        ]
        for model in (Client, Consultant, Project, Placement):
            assert await _count(db_session, model) == 0

    async def test_confirm_writes_and_a_reimport_changes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        content = _csv(
            _row(),
            _row(
                project_name="Fraud",
                start_date="2027-03-01",
                expected_end_date="2027-09-01",
            ),
        )

        first = await _import(manager_client, content, dry_run=False)
        again = await _import(manager_client, content, dry_run=True)

        assert first["applied"] is True
        assert first["summary"]["created"] == 2
        # The second row reused the client and consultant the first created
        assert await _count(db_session, Client) == 1
        assert await _count(db_session, Consultant) == 1
        assert await _count(db_session, Project) == 2
        assert await _count(db_session, Placement) == 2
        assert again["summary"]["unchanged"] == 2

    async def test_any_row_error_writes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        content = _csv(_row(), _row(consultant_full_name="X", start_date="soon"))

        body = await _import(manager_client, content, dry_run=False)

        assert body["applied"] is False
        assert body["summary"]["errors"] == 1
        assert body["rows"][1]["errors"] == [
            "start_date 'soon' is not a date (YYYY-MM-DD or DD/MM/YYYY)"
        ]
        # The good row was not written either
        assert body["rows"][0]["outcome"] == "create"
        assert await _count(db_session, Placement) == 0


class TestUpdates:
    async def test_filled_cells_overwrite_and_blank_cells_keep(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _import(
            manager_client,
            _csv(_row(rate_band="B", extension_status="due")),
            dry_run=False,
        )

        body = await _import(
            manager_client,
            _csv(
                _row(
                    expected_end_date="2027-05-01",
                    rate_band="",
                    extension_status="Requested",
                )
            ),
            dry_run=False,
        )

        row = body["rows"][0]
        assert row["outcome"] == "update"
        assert "placement expected_end_date: 2027-02-17 -> 2027-05-01" in row["changes"]
        assert "placement extension_status: due -> requested" in row["changes"]
        placement = (await db_session.execute(select(Placement))).scalar_one()
        await db_session.refresh(placement)
        assert placement.rate_band == "B"
        assert placement.extension_status == "requested"

    async def test_consultant_entered_by_name_gains_the_email(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _import(manager_client, _csv(_row(consultant_email="")), dry_run=False)

        body = await _import(manager_client, _csv(_row()), dry_run=False)

        assert (
            "consultant Vibin Cholayil email: vibin@example.com"
            in body["rows"][0]["changes"]
        )
        assert await _count(db_session, Consultant) == 1

    async def test_two_consultants_with_one_name_need_an_email(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        db_session.add_all(
            [Consultant(full_name="Divya"), Consultant(full_name="divya")]
        )
        await db_session.flush()

        body = await _import(
            manager_client,
            _csv(_row(consultant_full_name="Divya", consultant_email="")),
            dry_run=True,
        )

        assert body["rows"][0]["errors"] == [
            "several consultants are named Divya; add consultant_email to say which"
        ]
        assert body["rows"][0]["changes"] == []


class TestPeople:
    async def test_people_are_existing_users_with_a_role(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _user(db_session, "pat", Role.PS)
        await _user(db_session, "norole", None)

        body = await _import(
            manager_client,
            _csv(
                _row(ps_email="PAT@example.com"),
                _row(project_name="Fraud", sme_email="norole@example.com"),
                _row(project_name="Cards", tech_lead_email="ghost@example.com"),
            ),
            dry_run=True,
        )

        ok, no_role, unknown = body["rows"]
        assert ok["outcome"] == "create"
        assert ok["warnings"] == []
        assert "sme_email norole@example.com: no active user" in no_role["errors"][0]
        assert (
            "tech_lead_email ghost@example.com: no active user" in unknown["errors"][0]
        )

    async def test_a_different_role_is_a_warning(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        manager = await _user(db_session, "boss", Role.PMO_MANAGER)

        body = await _import(
            manager_client, _csv(_row(ps_email="boss@example.com")), dry_run=False
        )

        assert body["applied"] is True
        assert body["rows"][0]["warnings"] == [
            "ps_email boss@example.com is a pmo_manager, not a ps"
        ]
        placement = (await db_session.execute(select(Placement))).scalar_one()
        assert placement.ps_user_id == manager.id


class TestFileChecks:
    async def test_not_a_csv_is_refused(self, manager_client: AsyncClient) -> None:
        response = await manager_client.post(
            PATH, files={"file": ("register.xlsx", b"x", "application/octet-stream")}
        )

        assert response.status_code == 422

    async def test_scoped_roles_cannot_import(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post(
            PATH, files={"file": ("register.csv", _csv(_row()), "text/csv")}
        )

        assert response.status_code == 403
