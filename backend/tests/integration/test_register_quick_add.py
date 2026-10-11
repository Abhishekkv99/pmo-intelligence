"""The register quick add against a real database, through the route.

Pinned here: a dry run writes nothing; a Confirm writes every line or none;
pasting the same lines again changes nothing; a later end date or stack
updates the placement, found by consultant, client and start date even after
its project is renamed; a new placement goes under the client's "To be
confirmed" project; only the editing roles may use it.
"""

from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConsultantStatus, ExtensionStatus, PlacementStatus
from app.models.register import Client, Consultant, Placement, Project

pytestmark = pytest.mark.asyncio

PATH = "/api/v1/register/quick-add"
LINE = "PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027"
OTHER = "PRJ ITC BD – Asha Rao – wtw – 1-10-26 – 31-3-27"


async def _add(
    client: AsyncClient, lines: list[str], *, dry_run: bool
) -> dict[str, Any]:
    response = await client.post(
        PATH, params={"dry_run": str(dry_run).lower()}, json={"lines": lines}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _count(db: AsyncSession, model: type) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


class TestDryRunAndConfirm:
    async def test_dry_run_previews_and_writes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        body = await _add(manager_client, [LINE], dry_run=True)

        assert body["dry_run"] is True
        assert body["applied"] is False
        assert body["summary"] == {
            "lines": 1,
            "created": 1,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
        }
        assert body["lines"] == [
            {
                "line": 1,
                "text": LINE,
                "outcome": "create",
                "stack": "DS",
                "consultant": "Zeeshan Abbas Jaffar",
                "client": "WTW",
                "start_date": "2026-09-21",
                "expected_end_date": "2027-03-21",
                "changes": [
                    "client WTW: created",
                    "consultant Zeeshan Abbas Jaffar: created",
                    "project WTW / To be confirmed: created",
                    "placement 2026-09-21 to 2027-03-21: created",
                ],
                "errors": [],
            }
        ]
        for model in (Client, Consultant, Project, Placement):
            assert await _count(db_session, model) == 0

    async def test_confirm_writes_the_register(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        body = await _add(manager_client, [LINE, "", OTHER], dry_run=False)

        assert body["applied"] is True
        assert body["summary"]["created"] == 2
        # A blank line is skipped, and the line numbers stay those sent
        assert [line["line"] for line in body["lines"]] == [1, 3]
        # The second line found the client by its normalised name
        assert await _count(db_session, Client) == 1
        assert await _count(db_session, Consultant) == 2
        assert await _count(db_session, Project) == 1
        project = (await db_session.execute(select(Project))).scalar_one()
        assert project.name == "To be confirmed"

        placements = {
            p.stack: p
            for p in (await db_session.execute(select(Placement))).scalars().all()
        }
        assert set(placements) == {"DS", "BD"}
        ds = placements["DS"]
        assert ds.project_id == project.id
        assert (ds.start_date, ds.expected_end_date) == (
            date(2026, 9, 21),
            date(2027, 3, 21),
        )
        assert ds.status == PlacementStatus.ACTIVE.value
        assert ds.extension_status == ExtensionStatus.NOT_DUE.value
        consultant = await db_session.get(Consultant, ds.consultant_id)
        assert consultant is not None
        assert consultant.full_name == "Zeeshan Abbas Jaffar"
        assert consultant.email is None
        assert consultant.status == ConsultantStatus.PLACED.value

    async def test_the_same_lines_again_change_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _add(manager_client, [LINE, OTHER], dry_run=False)

        again = await _add(manager_client, [LINE, OTHER], dry_run=False)

        assert again["applied"] is True
        assert again["summary"]["unchanged"] == 2
        assert [line["changes"] for line in again["lines"]] == [[], []]
        assert await _count(db_session, Placement) == 2

    async def test_any_line_error_writes_nothing(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        bad = "PRJ ITC DS - Asha Rao - WTW - soon - 21/03/2027"

        body = await _add(manager_client, [LINE, bad], dry_run=False)

        assert body["applied"] is False
        assert body["summary"]["errors"] == 1
        assert body["lines"][1]["outcome"] == "error"
        assert body["lines"][1]["errors"] == [
            "the start date 'soon' is not D/M/YYYY or D-M-YY"
        ]
        assert body["lines"][1]["consultant"] is None
        # The good line was not written either
        assert body["lines"][0]["outcome"] == "create"
        for model in (Client, Consultant, Project, Placement):
            assert await _count(db_session, model) == 0


class TestUpdates:
    async def test_a_new_end_date_and_stack_update_the_placement(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _add(manager_client, [LINE], dry_run=False)
        later = "PRJ ITC DE - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/06/2027"

        body = await _add(manager_client, [later], dry_run=False)

        assert body["lines"][0]["outcome"] == "update"
        assert body["lines"][0]["changes"] == [
            "end date: 2027-03-21 -> 2027-06-21",
            "stack: DS -> DE",
        ]
        placement = (await db_session.execute(select(Placement))).scalar_one()
        await db_session.refresh(placement)
        assert placement.expected_end_date == date(2027, 6, 21)
        assert placement.stack == "DE"

    async def test_a_renamed_project_keeps_its_placement(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _add(manager_client, [LINE], dry_run=False)
        project = (await db_session.execute(select(Project))).scalar_one()
        response = await manager_client.patch(
            f"/api/v1/projects/{project.id}", json={"name": "Claims Platform"}
        )
        assert response.status_code == 200

        body = await _add(manager_client, [LINE], dry_run=False)

        assert body["lines"][0]["outcome"] == "unchanged"
        assert await _count(db_session, Placement) == 1
        # No new "To be confirmed" project was made for it
        assert await _count(db_session, Project) == 1

    async def test_a_new_start_date_is_a_new_placement(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _add(manager_client, [LINE], dry_run=False)
        renewal = "PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 22/3/2027 - 21/09/2027"

        body = await _add(manager_client, [renewal], dry_run=False)

        assert body["lines"][0]["changes"] == [
            "placement 2027-03-22 to 2027-09-21: created"
        ]
        assert await _count(db_session, Consultant) == 1
        assert await _count(db_session, Placement) == 2

    async def test_two_consultants_with_one_name_are_an_error(
        self, manager_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        for email in ("z1@example.com", "z2@example.com"):
            response = await manager_client.post(
                "/api/v1/consultants",
                json={"full_name": "Zeeshan Abbas Jaffar", "email": email},
            )
            assert response.status_code == 201

        body = await _add(manager_client, [LINE], dry_run=False)

        assert body["applied"] is False
        assert body["lines"][0]["errors"] == [
            "several consultants are named Zeeshan Abbas Jaffar; "
            "add this placement on the Placements tab instead"
        ]
        assert await _count(db_session, Client) == 0


class TestAccess:
    async def test_no_lines_is_refused(self, manager_client: AsyncClient) -> None:
        response = await manager_client.post(
            PATH, params={"dry_run": "true"}, json={"lines": ["   ", ""]}
        )

        assert response.status_code == 422

    async def test_scoped_roles_cannot_quick_add(
        self, authenticated_client: AsyncClient
    ) -> None:
        response = await authenticated_client.post(PATH, json={"lines": [LINE]})

        assert response.status_code == 403
