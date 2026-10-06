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
    "alembic_version",
    "clients",
    "consultants",
    "placements",
    "processing_costs",
    "processing_jobs",
    "projects",
    "refresh_tokens",
    "users",
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
