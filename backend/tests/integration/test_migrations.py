"""The Alembic migrations against a real, empty pgvector database.

The other integration tests build the schema with ``create_all``, so without
this test a migration could drift from the models, or fail on a fresh
database, and nothing would notice until a deploy's migration container did.
Alembic's env.py runs its own event loop, so it is driven in a subprocess.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_NAME = "migration_check"

EXPECTED_TABLES = {
    "access_log",
    "actions",
    "alembic_version",
    "clients",
    "consultants",
    "health_snapshots",
    "issues",
    "placements",
    "processing_costs",
    "processing_jobs",
    "projects",
    "recording_folders",
    "recording_scans",
    "refresh_tokens",
    "risk_flags",
    "session_transcripts",
    "sessions",
    "signals",
    "source_recordings",
    "users",
}

SESSION_TABLES = {
    "recording_folders",
    "session_transcripts",
    "sessions",
    "source_recordings",
}


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
async def fresh_database_url(engine: AsyncEngine, database_url: str) -> str:
    """A brand-new empty database on the test container, dropped afterwards."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
        await conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
    url = database_url.rsplit("/", 1)[0] + f"/{DB_NAME}"
    yield url
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)"))


async def _tables(url: str) -> set[str]:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {row[0] for row in rows}
    finally:
        await check.dispose()


async def _user_columns(url: str) -> set[str]:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'users'"
                )
            )
            return {row[0] for row in rows}
    finally:
        await check.dispose()


async def _cost_session_foreign_keys(url: str) -> int:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            count = await conn.scalar(
                text(
                    "SELECT count(*) FROM information_schema.table_constraints "
                    "WHERE table_name = 'processing_costs' "
                    "AND constraint_name = 'processing_costs_session_id_fkey'"
                )
            )
            return int(count or 0)
    finally:
        await check.dispose()


SIGNAL_TABLES = {"actions", "issues", "signals"}
HEALTH_TABLES = {"health_snapshots", "risk_flags"}


async def _signal_columns_and_indexes(url: str) -> tuple[set[str], set[str]]:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            columns = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'signals'"
                )
            )
            indexes = await conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'signals'")
            )
            return {row[0] for row in columns}, {row[0] for row in indexes}
    finally:
        await check.dispose()


async def _transcript_columns(url: str) -> set[str]:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'session_transcripts'"
                )
            )
            return {row[0] for row in rows}
    finally:
        await check.dispose()


async def _snapshot_columns(url: str) -> set[str]:
    return await _columns(url, "health_snapshots")


async def _columns(url: str, table: str) -> set[str]:
    check = create_async_engine(url)
    try:
        async with check.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table"
                ),
                {"table": table},
            )
            return {row[0] for row in rows}
    finally:
        await check.dispose()


TECHNICAL_TREND_COLUMNS = {"technical_trend", "technical_trend_delta"}

MS_TOKEN_COLUMNS = {"ms_access_token", "ms_refresh_token", "ms_token_expires_at"}


class TestMigrations:
    async def test_upgrade_head_builds_the_schema_without_drift(
        self, fresh_database_url: str
    ) -> None:
        upgrade = _alembic(fresh_database_url, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        assert await _tables(fresh_database_url) == EXPECTED_TABLES

        # The models and the migrations describe the same schema.
        check = _alembic(fresh_database_url, "check")
        assert check.returncode == 0, check.stdout + check.stderr

    async def test_downgrade_base_then_upgrade_again(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "head").returncode == 0

        downgrade = _alembic(fresh_database_url, "downgrade", "base")
        assert downgrade.returncode == 0, downgrade.stderr
        assert await _tables(fresh_database_url) == {"alembic_version"}

        again = _alembic(fresh_database_url, "upgrade", "head")
        assert again.returncode == 0, again.stderr

    async def test_002_drops_the_microsoft_token_columns_and_restores_them(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "001").returncode == 0
        assert MS_TOKEN_COLUMNS.issubset(await _user_columns(fresh_database_url))

        assert _alembic(fresh_database_url, "upgrade", "002").returncode == 0
        assert not MS_TOKEN_COLUMNS & await _user_columns(fresh_database_url)

        assert _alembic(fresh_database_url, "downgrade", "001").returncode == 0
        assert MS_TOKEN_COLUMNS.issubset(await _user_columns(fresh_database_url))

    async def test_003_adds_the_session_tables_and_the_cost_key_and_removes_them(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "002").returncode == 0
        assert not SESSION_TABLES & await _tables(fresh_database_url)

        upgrade = _alembic(fresh_database_url, "upgrade", "003")
        assert upgrade.returncode == 0, upgrade.stderr
        assert SESSION_TABLES.issubset(await _tables(fresh_database_url))
        assert await _cost_session_foreign_keys(fresh_database_url) == 1

        downgrade = _alembic(fresh_database_url, "downgrade", "002")
        assert downgrade.returncode == 0, downgrade.stderr
        assert not SESSION_TABLES & await _tables(fresh_database_url)
        assert await _cost_session_foreign_keys(fresh_database_url) == 0

    async def test_004_adds_the_recording_scans_table_and_removes_it(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "003").returncode == 0
        assert "recording_scans" not in await _tables(fresh_database_url)

        upgrade = _alembic(fresh_database_url, "upgrade", "004")
        assert upgrade.returncode == 0, upgrade.stderr
        assert "recording_scans" in await _tables(fresh_database_url)

        downgrade = _alembic(fresh_database_url, "downgrade", "003")
        assert downgrade.returncode == 0, downgrade.stderr
        assert "recording_scans" not in await _tables(fresh_database_url)

    async def test_005_adds_signals_issues_actions_and_project_phase_and_removes_them(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "004").returncode == 0
        assert not SIGNAL_TABLES & await _tables(fresh_database_url)

        upgrade = _alembic(fresh_database_url, "upgrade", "005")
        assert upgrade.returncode == 0, upgrade.stderr
        assert SIGNAL_TABLES.issubset(await _tables(fresh_database_url))
        assert "project_phase" in await _transcript_columns(fresh_database_url)

        downgrade = _alembic(fresh_database_url, "downgrade", "004")
        assert downgrade.returncode == 0, downgrade.stderr
        assert not SIGNAL_TABLES & await _tables(fresh_database_url)
        assert "project_phase" not in await _transcript_columns(fresh_database_url)

    async def test_006_adds_health_tables_indicator_and_hnsw_index_and_removes_them(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "005").returncode == 0
        assert not HEALTH_TABLES & await _tables(fresh_database_url)

        upgrade = _alembic(fresh_database_url, "upgrade", "006")
        assert upgrade.returncode == 0, upgrade.stderr
        assert HEALTH_TABLES.issubset(await _tables(fresh_database_url))
        columns, indexes = await _signal_columns_and_indexes(fresh_database_url)
        assert "indicator" in columns
        assert "ix_signals_embedding_hnsw" in indexes

        downgrade = _alembic(fresh_database_url, "downgrade", "005")
        assert downgrade.returncode == 0, downgrade.stderr
        assert not HEALTH_TABLES & await _tables(fresh_database_url)
        columns, indexes = await _signal_columns_and_indexes(fresh_database_url)
        assert "indicator" not in columns
        assert "ix_signals_embedding_hnsw" not in indexes

    async def test_007_adds_the_technical_trend_to_snapshots_and_removes_it(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "006").returncode == 0
        assert not TECHNICAL_TREND_COLUMNS & await _snapshot_columns(fresh_database_url)

        upgrade = _alembic(fresh_database_url, "upgrade", "007")
        assert upgrade.returncode == 0, upgrade.stderr
        assert TECHNICAL_TREND_COLUMNS.issubset(
            await _snapshot_columns(fresh_database_url)
        )

        downgrade = _alembic(fresh_database_url, "downgrade", "006")
        assert downgrade.returncode == 0, downgrade.stderr
        assert not TECHNICAL_TREND_COLUMNS & await _snapshot_columns(fresh_database_url)

    async def test_008_adds_the_placement_stack_and_removes_it(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "007").returncode == 0
        assert "stack" not in await _columns(fresh_database_url, "placements")

        upgrade = _alembic(fresh_database_url, "upgrade", "008")
        assert upgrade.returncode == 0, upgrade.stderr
        assert "stack" in await _columns(fresh_database_url, "placements")

        downgrade = _alembic(fresh_database_url, "downgrade", "007")
        assert downgrade.returncode == 0, downgrade.stderr
        assert "stack" not in await _columns(fresh_database_url, "placements")

    async def test_009_turns_the_tech_lead_into_the_consultants_cdm_and_back(
        self, fresh_database_url: str
    ) -> None:
        assert _alembic(fresh_database_url, "upgrade", "008").returncode == 0
        engine = create_async_engine(fresh_database_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, full_name, role, is_active,"
                        " auth_provider, created_at, updated_at) VALUES"
                        " ('00000000-0000-0000-0000-0000000000a1', 'lee@x.com',"
                        " 'Lee', 'tech_lead', true, 'local', now(), now())"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO clients (id, name, normalized_name, created_at,"
                        " updated_at) VALUES ('00000000-0000-0000-0000-0000000000c1',"
                        " 'Acme', 'acme', now(), now())"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO projects (id, client_id, name, tech_lead_user_id,"
                        " created_at, updated_at) VALUES"
                        " ('00000000-0000-0000-0000-0000000000b1',"
                        " '00000000-0000-0000-0000-0000000000c1', 'Payments',"
                        " '00000000-0000-0000-0000-0000000000a1', now(), now())"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO consultants (id, full_name, skills, status,"
                        " created_at, updated_at) VALUES"
                        " ('00000000-0000-0000-0000-0000000000d1', 'Jo', '[]',"
                        " 'placed', now(), now())"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO placements (id, consultant_id, project_id,"
                        " start_date, extension_status, status, created_at,"
                        " updated_at) VALUES ('00000000-0000-0000-0000-0000000000e1',"
                        " '00000000-0000-0000-0000-0000000000d1',"
                        " '00000000-0000-0000-0000-0000000000b1', '2026-09-01',"
                        " 'not_due', 'active', now(), now())"
                    )
                )

            upgrade = _alembic(fresh_database_url, "upgrade", "009")
            assert upgrade.returncode == 0, upgrade.stderr
            async with engine.connect() as conn:
                role = (await conn.execute(text("SELECT role FROM users"))).scalar_one()
                cdm = (
                    await conn.execute(text("SELECT cdm_user_id FROM consultants"))
                ).scalar_one()
            assert role == "cdm"
            assert str(cdm) == "00000000-0000-0000-0000-0000000000a1"
            assert "tech_lead_user_id" not in await _columns(
                fresh_database_url, "projects"
            )

            downgrade = _alembic(fresh_database_url, "downgrade", "008")
            assert downgrade.returncode == 0, downgrade.stderr
            async with engine.connect() as conn:
                role = (await conn.execute(text("SELECT role FROM users"))).scalar_one()
                lead = (
                    await conn.execute(text("SELECT tech_lead_user_id FROM projects"))
                ).scalar_one()
            assert role == "tech_lead"
            assert str(lead) == "00000000-0000-0000-0000-0000000000a1"
            assert "cdm_user_id" not in await _columns(
                fresh_database_url, "consultants"
            )
        finally:
            await engine.dispose()
