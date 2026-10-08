"""The request's session commits before the response is sent.

FastAPI ends a yield dependency after the response by default, which let a
201 reach the browser before its row was committed: a list read straight
after a save missed the new row, and a commit that failed still answered
success. ``DbSession`` declares the session with ``scope="function"``; these
tests pin that every route uses it and that a failed commit is an error.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.dependencies import DbSession, get_db
from app.main import app


def _session_scopes(dependant: Dependant) -> list[str | None]:
    scopes: list[str | None] = []
    for sub in dependant.dependencies:
        if sub.call is get_db:
            scopes.append(sub.scope)
        scopes.extend(_session_scopes(sub))
    return scopes


ROUTES = [r for r in app.routes if isinstance(r, APIRoute)]


def test_routes_take_a_session() -> None:
    # Guards against the walk silently finding nothing
    assert sum(bool(_session_scopes(r.dependant)) for r in ROUTES) > 10


@pytest.mark.parametrize(
    "route", ROUTES, ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
def test_every_session_commits_before_the_response(route: APIRoute) -> None:
    assert all(scope == "function" for scope in _session_scopes(route.dependant))


async def test_a_failed_commit_answers_an_error_not_success() -> None:
    probe = FastAPI()

    @probe.post("/thing", status_code=201)
    async def create(db: DbSession) -> dict[str, str]:
        return {"status": "created"}

    async def failing_commit() -> AsyncGenerator[Any]:
        yield object()
        raise RuntimeError("commit failed")

    probe.dependency_overrides[get_db] = failing_commit
    transport = ASGITransport(app=probe, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/thing")

    assert response.status_code == 500
