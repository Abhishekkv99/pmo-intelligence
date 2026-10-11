"""The placement-scope dependencies against a real database.

No product route is addressed by a placement id yet, so a throwaway app
mounts the two dependencies exactly as a route would. What is pinned here is
the rule from docs/PRD.md: a user sees the placements that name them (PS,
SME, or the consultant's CDM, who replaced the PRD's tech lead) or
everything (PMO manager, admin); anything else answers 404,
indistinguishable from a missing placement, and only a permitted read of
consultant data writes an access_log row.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_repo import UserRepository
from app.dependencies import (
    LoggedPlacementScope,
    PlacementScope,
    get_current_user,
    get_db,
)
from app.models.access_log import AccessLog
from app.models.enums import Role
from app.models.register import Client, Consultant, Placement, Project
from app.models.user import User
from app.services.auth_service import AuthService
from app.utils.exceptions import AppError


def _scope_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    @app.get("/placements/{placement_id}")
    async def read(placement: PlacementScope) -> dict[str, str]:
        return {"id": str(placement.id)}

    @app.get("/placements/{placement_id}/consultant")
    async def read_logged(placement: LoggedPlacementScope) -> dict[str, str]:
        return {"id": str(placement.id)}

    return app


@dataclass
class _World:
    placement: Placement
    manager: User
    admin: User
    ps: User
    sme: User
    cdm: User
    other_ps: User
    no_role: User


async def _user(db: AsyncSession, name: str, role: Role | None) -> User:
    return await UserRepository(db).create(
        email=f"{name}@example.com",
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=name,
        role=role.value if role else None,
    )


@pytest.fixture
async def world(db_session: AsyncSession) -> _World:
    manager = await _user(db_session, "manager", Role.PMO_MANAGER)
    admin = await _user(db_session, "admin", Role.ADMIN)
    ps = await _user(db_session, "ps", Role.PS)
    sme = await _user(db_session, "sme", Role.SME)
    cdm = await _user(db_session, "cdm", Role.CDM)
    other_ps = await _user(db_session, "other-ps", Role.PS)
    no_role = await _user(db_session, "no-role", None)

    client = Client(name="Acme Bank", normalized_name="acme bank")
    db_session.add(client)
    await db_session.flush()
    project = Project(client_id=client.id, name="Payments")
    consultant = Consultant(full_name="Jo Bloggs", cdm_user_id=cdm.id)
    db_session.add_all([project, consultant])
    await db_session.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date(2026, 9, 1),
        ps_user_id=ps.id,
        sme_user_id=sme.id,
    )
    db_session.add(placement)
    await db_session.flush()

    return _World(placement, manager, admin, ps, sme, cdm, other_ps, no_role)


@asynccontextmanager
async def _client_as(db: AsyncSession, user: User) -> AsyncGenerator[AsyncClient]:
    app = _scope_app()

    async def _db() -> AsyncGenerator[AsyncSession]:
        yield db

    async def _current_user() -> User:
        await db.refresh(user)
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _current_user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def _get(db: AsyncSession, user: User, path: str) -> tuple[int, object]:
    async with _client_as(db, user) as client:
        response = await client.get(path)
    return response.status_code, response.json()


async def _access_rows(db: AsyncSession, placement_id: uuid.UUID) -> list[AccessLog]:
    result = await db.execute(
        select(AccessLog).where(AccessLog.placement_id == placement_id)
    )
    return list(result.scalars().all())


class TestWhoCanRead:
    @pytest.mark.parametrize("who", ["manager", "admin", "ps", "sme", "cdm"], ids=str)
    async def test_allowed(
        self, db_session: AsyncSession, world: _World, who: str
    ) -> None:
        user = getattr(world, who)
        status, body = await _get(db_session, user, f"/placements/{world.placement.id}")

        assert status == 200
        assert body == {"id": str(world.placement.id)}

    async def test_a_cdm_reads_every_placement_of_their_consultant_only(
        self, db_session: AsyncSession, world: _World
    ) -> None:
        later = Placement(
            consultant_id=world.placement.consultant_id,
            project_id=world.placement.project_id,
            start_date=date(2027, 3, 1),
        )
        someone_else = Consultant(full_name="Ann Other")
        db_session.add_all([later, someone_else])
        await db_session.flush()
        theirs = Placement(
            consultant_id=someone_else.id,
            project_id=world.placement.project_id,
            start_date=date(2026, 9, 1),
            ps_user_id=world.ps.id,
        )
        db_session.add(theirs)
        await db_session.flush()

        mine = await _get(db_session, world.cdm, f"/placements/{later.id}")
        other = await _get(db_session, world.cdm, f"/placements/{theirs.id}")

        assert mine[0] == 200
        assert other[0] == 404

    @pytest.mark.parametrize("who", ["other_ps", "no_role"], ids=str)
    async def test_denied_reads_exactly_like_a_missing_placement(
        self, db_session: AsyncSession, world: _World, who: str
    ) -> None:
        user = getattr(world, who)
        denied = await _get(db_session, user, f"/placements/{world.placement.id}")

        missing_id = uuid.uuid4()
        missing = await _get(db_session, world.manager, f"/placements/{missing_id}")

        assert denied[0] == missing[0] == 404
        assert denied[1] == {
            "detail": f"Placement with id '{world.placement.id}' not found"
        }
        assert missing[1] == {"detail": f"Placement with id '{missing_id}' not found"}


class TestAccessLog:
    async def test_a_logged_read_writes_one_row_with_the_route(
        self, db_session: AsyncSession, world: _World
    ) -> None:
        path = f"/placements/{world.placement.id}/consultant"
        status, _ = await _get(db_session, world.ps, path)

        rows = await _access_rows(db_session, world.placement.id)
        assert status == 200
        assert len(rows) == 1
        assert rows[0].user_id == world.ps.id
        assert rows[0].route == path
        assert rows[0].at is not None

    async def test_an_unlogged_read_writes_nothing(
        self, db_session: AsyncSession, world: _World
    ) -> None:
        await _get(db_session, world.manager, f"/placements/{world.placement.id}")

        assert await _access_rows(db_session, world.placement.id) == []

    async def test_a_denied_read_writes_nothing(
        self, db_session: AsyncSession, world: _World
    ) -> None:
        path = f"/placements/{world.placement.id}/consultant"
        status, _ = await _get(db_session, world.other_ps, path)

        assert status == 404
        assert await _access_rows(db_session, world.placement.id) == []
