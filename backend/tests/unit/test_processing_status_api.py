"""Unit tests for GET /processing/status - the processing queue view.

The route reads the per-test queue's snapshot and the process RSS; it is
gated on a global role (the queue is shared by every placement).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app
from app.models.user import User
from app.services.processing_queue import (
    CHAT_PRIORITY,
    Job,
    QueueSnapshot,
    RunningJob,
    get_processing_queue,
)

ROUTE = "app.api.v1.processing"
PATH = "/api/v1/processing/status"

pytestmark = pytest.mark.asyncio


def _mock_user(role: str | None) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.role = role
    return user


async def _client_as(role: str | None) -> AsyncGenerator[AsyncClient]:
    app.dependency_overrides[get_current_user] = lambda: _mock_user(role)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client() -> AsyncGenerator[AsyncClient]:
    async for client in _client_as("pmo_manager"):
        yield client


class TestProcessingStatus:
    async def test_idle_queue(self, admin_client: AsyncClient) -> None:
        with patch(f"{ROUTE}.current_rss_mib", return_value=123.4):
            response = await admin_client.get(PATH)

        assert response.status_code == 200
        assert response.json() == {
            "queue_depth": 0,
            "capacity": get_processing_queue().capacity,
            "running": [],
            "rss_mib": 123.4,
            "memory_diagnostics_enabled": False,
        }

    async def test_depth_counts_pending_jobs_of_every_kind(
        self, admin_client: AsyncClient
    ) -> None:
        queue = get_processing_queue()
        queue.enqueue(Job("session_pipeline", uuid.uuid4()))
        queue.enqueue(Job("chat_pipeline", uuid.uuid4(), CHAT_PRIORITY))
        queue.enqueue(Job("health_recompute", uuid.uuid4()))

        with patch(f"{ROUTE}.current_rss_mib", return_value=None):
            response = await admin_client.get(PATH)

        assert response.status_code == 200
        assert response.json()["queue_depth"] == 3

    async def test_running_jobs_are_listed_with_start_time_and_worker(
        self, admin_client: AsyncClient
    ) -> None:
        session_id = uuid.uuid4()
        started = datetime(2026, 9, 21, 20, 15, tzinfo=UTC)
        snapshot = QueueSnapshot(
            depth=2,
            capacity=1,
            running=(
                RunningJob(
                    job=Job("session_pipeline", session_id),
                    started_at=started,
                    worker=0,
                ),
            ),
            pending=(),
        )

        with (
            patch.object(get_processing_queue(), "snapshot", return_value=snapshot),
            patch(f"{ROUTE}.current_rss_mib", return_value=512.0),
        ):
            response = await admin_client.get(PATH)

        assert response.status_code == 200
        body = response.json()
        assert body["queue_depth"] == 2
        assert body["capacity"] == 1
        assert body["running"] == [
            {
                "kind": "session_pipeline",
                "id": str(session_id),
                "started_at": "2026-09-21T20:15:00Z",
                "worker": 0,
            }
        ]

    async def test_rss_is_null_where_proc_is_unavailable(
        self, admin_client: AsyncClient
    ) -> None:
        with patch(f"{ROUTE}.current_rss_mib", return_value=None):
            response = await admin_client.get(PATH)

        assert response.status_code == 200
        assert response.json()["rss_mib"] is None

    async def test_reports_the_diagnostics_setting(
        self, admin_client: AsyncClient
    ) -> None:
        with (
            patch(f"{ROUTE}.current_rss_mib", return_value=None),
            patch(f"{ROUTE}.settings") as settings,
        ):
            settings.memory_diagnostics_enabled = True
            response = await admin_client.get(PATH)

        assert response.json()["memory_diagnostics_enabled"] is True

    async def test_admin_role_is_allowed(self) -> None:
        with patch(f"{ROUTE}.current_rss_mib", return_value=None):
            async for client in _client_as("admin"):
                response = await client.get(PATH)

        assert response.status_code == 200

    @pytest.mark.parametrize("role", ["ps", "sme", "cdm", None])
    async def test_other_roles_and_no_role_are_a_403(self, role: str | None) -> None:
        async for client in _client_as(role):
            response = await client.get(PATH)

        assert response.status_code == 403
        assert response.json() == {"detail": "Not authorised for this operation"}

    async def test_requires_authentication(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(PATH)

        assert response.status_code == 401
