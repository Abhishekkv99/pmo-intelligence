"""The health jobs against a real database: the takeover catch-up, the daily
fan-out, the recompute runner, and the register routes queuing recomputes
after their commit."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import PlacementStatus, SnapshotReason
from app.models.health import HealthSnapshot
from app.models.register import Client, Consultant, Placement, Project
from app.models.signal import Signal
from app.services import health_jobs
from app.services.health_jobs import (
    RECOMPUTE_JOB_KIND,
    daily_job,
    recompute_job,
    requeue_stale_placements,
    run_daily_job,
    run_recompute_job,
    stale_placements,
)
from app.services.processing_queue import (
    BACKLOG_PRIORITY,
    ProcessingQueue,
    get_processing_queue,
    set_processing_queue,
)

# Friday 9 October 2026, 13:00 in London: today's 06:00 run was at 05:00 UTC
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=10)


@pytest.fixture(autouse=True)
def _use_test_session(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(health_jobs, "async_session_factory", factory)


@pytest.fixture
async def client_row(db_session: AsyncSession) -> Client:
    row = Client(name="Acme", normalized_name=f"acme {uuid.uuid4()}")
    db_session.add(row)
    await db_session.flush()
    return row


async def _placement(
    db: AsyncSession,
    client_row: Client,
    *,
    status: PlacementStatus = PlacementStatus.ACTIVE,
    edited: datetime = LONG_AGO,
    project_edited: datetime = LONG_AGO,
    snapshot_at: datetime | None = None,
    signal_stored: datetime | None = None,
) -> uuid.UUID:
    consultant = Consultant(full_name="Priya Shah")
    project = Project(
        client_id=client_row.id,
        name=f"Project {uuid.uuid4()}",
        created_at=LONG_AGO,
        updated_at=project_edited,
    )
    db.add_all([consultant, project])
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id,
        project_id=project.id,
        start_date=date(2026, 8, 1),
        status=status.value,
        created_at=LONG_AGO,
        updated_at=edited,
    )
    db.add(placement)
    await db.flush()
    if snapshot_at is not None:
        db.add(
            HealthSnapshot(
                placement_id=placement.id,
                computed_at=snapshot_at,
                reason="call",
                scored=False,
                weights_version="v1",
            )
        )
    if signal_stored is not None:
        db.add(
            Signal(
                placement_id=placement.id,
                source_kind="session",
                source_id=uuid.uuid4(),
                category="client",
                dimension="delivery",
                polarity="negative",
                severity=2,
                confidence=0.9,
                quote="The client asked again.",
                occurred_at=signal_stored,
                created_at=signal_stored,
            )
        )
    await db.flush()
    return placement.id


class TestCatchUp:
    async def test_out_of_date_placements_are_found(
        self, db_session: AsyncSession, client_row: Client
    ) -> None:
        day = timedelta(days=1)
        never = await _placement(db_session, client_row, status=PlacementStatus.ENDED)
        fresh = await _placement(
            db_session,
            client_row,
            snapshot_at=NOW - day,
            signal_stored=NOW - 5 * day,
        )
        new_signal = await _placement(
            db_session, client_row, snapshot_at=NOW - 5 * day, signal_stored=NOW - day
        )
        edited = await _placement(
            db_session, client_row, edited=NOW - day, snapshot_at=NOW - 5 * day
        )
        project_edited = await _placement(
            db_session,
            client_row,
            project_edited=NOW - day,
            snapshot_at=NOW - 5 * day,
        )

        stale = await stale_placements(NOW)

        assert set(stale) == {never, new_signal, edited, project_edited}
        assert fresh not in stale

    async def test_with_the_daily_run_on_a_missed_run_is_caught_up(
        self,
        db_session: AsyncSession,
        client_row: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "health_daily_enabled", True)
        before_run = NOW - timedelta(hours=8)  # 04:00 UTC, before 05:00
        after_run = NOW - timedelta(hours=1)
        missed = await _placement(db_session, client_row, snapshot_at=before_run)
        done = await _placement(db_session, client_row, snapshot_at=after_run)
        ended = await _placement(
            db_session,
            client_row,
            status=PlacementStatus.ENDED,
            snapshot_at=before_run,
        )

        stale = await stale_placements(NOW)

        assert missed in stale
        assert done not in stale
        assert ended not in stale

    async def test_with_the_daily_run_off_an_old_snapshot_is_left(
        self, db_session: AsyncSession, client_row: Client
    ) -> None:
        old = await _placement(
            db_session, client_row, snapshot_at=NOW - timedelta(days=3)
        )

        assert old not in await stale_placements(NOW)

    async def test_the_takeover_queues_them_as_catch_up_at_backlog_priority(
        self, db_session: AsyncSession, client_row: Client
    ) -> None:
        never = await _placement(db_session, client_row)

        assert await requeue_stale_placements() >= 1

        [job] = [j for j in get_processing_queue().snapshot().pending if j.id == never]
        assert job == recompute_job(never, SnapshotReason.CATCH_UP)
        assert job.priority == BACKLOG_PRIORITY


class TestRunners:
    async def test_the_daily_job_queues_every_active_placement(
        self, db_session: AsyncSession, client_row: Client
    ) -> None:
        active = await _placement(db_session, client_row)
        ended = await _placement(
            db_session, client_row, status=PlacementStatus.TERMINATED
        )

        await run_daily_job(daily_job())

        queued = {j.id: j for j in get_processing_queue().snapshot().pending}
        assert queued[active] == recompute_job(active, SnapshotReason.DAILY)
        assert ended not in queued

    async def test_the_recompute_job_stores_a_snapshot_with_its_reason(
        self, db_session: AsyncSession, client_row: Client
    ) -> None:
        placement_id = await _placement(db_session, client_row)

        await run_recompute_job(recompute_job(placement_id, SnapshotReason.DAILY))

        snapshot = await db_session.scalar(
            select(HealthSnapshot).where(HealthSnapshot.placement_id == placement_id)
        )
        assert snapshot is not None
        assert snapshot.reason == "daily"


def _fresh_queue() -> None:
    """Start the next step from an empty (never started) queue."""
    set_processing_queue(ProcessingQueue(concurrency=1))


def _queued_recomputes() -> dict[uuid.UUID, str | None]:
    return {
        job.id: job.reason
        for job in get_processing_queue().snapshot().pending
        if job.kind == RECOMPUTE_JOB_KIND
    }


async def _post(client: AsyncClient, path: str, body: dict[str, Any]) -> Any:
    response = await client.post(f"/api/v1{path}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


class TestRegisterHooks:
    async def _world(self, client: AsyncClient) -> dict[str, Any]:
        client_row = await _post(client, "/clients", {"name": f"Bank {uuid.uuid4()}"})
        consultant = await _post(client, "/consultants", {"full_name": "Vibin C"})
        project = await _post(
            client, "/projects", {"client_id": client_row["id"], "name": "Payments"}
        )
        placement = await _post(
            client,
            "/placements",
            {
                "consultant_id": consultant["id"],
                "project_id": project["id"],
                "start_date": "2026-08-17",
            },
        )
        return {"consultant": consultant, "project": project, "placement": placement}

    async def test_creating_or_editing_a_placement_queues_its_recompute(
        self, manager_client: AsyncClient
    ) -> None:
        w = await self._world(manager_client)
        placement_id = uuid.UUID(w["placement"]["id"])
        # Creating a client, consultant or project queues nothing
        assert _queued_recomputes() == {placement_id: "register"}

        response = await manager_client.patch(
            f"/api/v1/placements/{placement_id}",
            json={"expected_end_date": "2026-10-30"},
        )

        assert response.status_code == 200
        # Still one job for the placement, waiting
        assert _queued_recomputes() == {placement_id: "register"}

    async def test_editing_a_project_queues_its_active_placements(
        self, manager_client: AsyncClient
    ) -> None:
        w = await self._world(manager_client)
        ended = await _post(
            manager_client,
            "/placements",
            {
                "consultant_id": w["consultant"]["id"],
                "project_id": w["project"]["id"],
                "start_date": "2025-01-06",
                "status": "ended",
            },
        )
        other = await self._world(manager_client)
        _fresh_queue()

        response = await manager_client.patch(
            f"/api/v1/projects/{w['project']['id']}",
            json={"client_manager_name": "Dana Lee"},
        )

        assert response.status_code == 200
        queued = _queued_recomputes()
        assert queued == {uuid.UUID(w["placement"]["id"]): "register"}
        assert uuid.UUID(ended["id"]) not in queued
        assert uuid.UUID(other["placement"]["id"]) not in queued

    async def test_an_applied_quick_add_queues_the_placements_it_created_or_changed(
        self, manager_client: AsyncClient
    ) -> None:
        def line(name: str, end: str = "17/02/2027") -> str:
            return f"PRJ ITC DS - {name} - Barclays - 17/8/2026 - {end}"

        async def run(lines: list[str], *, dry_run: bool) -> dict[str, Any]:
            response = await manager_client.post(
                "/api/v1/register/quick-add",
                params={"dry_run": str(dry_run).lower()},
                json={"lines": lines},
            )
            assert response.status_code == 200, response.text
            body: dict[str, Any] = response.json()
            return body

        first = [line("Vibin Cholayil"), line("Ann Lee")]
        assert (await run(first, dry_run=True))["applied"] is False
        assert _queued_recomputes() == {}

        assert (await run(first, dry_run=False))["applied"] is True
        created = _queued_recomputes()
        assert len(created) == 2
        assert set(created.values()) == {"register"}

        _fresh_queue()
        # One line changed, one the same: only the changed one is queued
        second = [line("Vibin Cholayil", end="17/05/2027"), line("Ann Lee")]
        assert (await run(second, dry_run=False))["applied"] is True

        [changed] = _queued_recomputes()
        assert changed in created
