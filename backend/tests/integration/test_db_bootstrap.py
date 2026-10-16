"""Integration tests for the database bootstrap against PostgreSQL 16 + pgvector.

Each test gets its own database and login, so ownership changes never touch
the shared test database.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

from app.cli import db_bootstrap
from app.cli.db_bootstrap import SECRET_PLACEHOLDER, BootstrapConfig, ensure_database


class FakeSecretsClient:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    async def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:  # noqa: N803
        return {"SecretString": json.dumps(self.values)}

    async def put_secret_value(
        self,
        *,
        SecretId: str,  # noqa: N803
        SecretString: str,  # noqa: N803
    ) -> dict[str, Any]:
        self.values = json.loads(SecretString)
        return {}


class FakeSession:
    """Stands in for aioboto3.Session; hands out one shared fake client."""

    def __init__(self, client: FakeSecretsClient) -> None:
        self._client = client

    def client(self, service: str, region_name: str) -> "FakeSession":
        assert service == "secretsmanager"
        return self

    async def __aenter__(self) -> FakeSecretsClient:
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
async def bootstrap_config(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[BootstrapConfig]:
    host = postgres_container.get_container_host_ip()
    port = int(postgres_container.get_exposed_port(5432))
    suffix = uuid.uuid4().hex[:8]
    database = f"bootstrap_{suffix}"
    app_user = f"pmo_app_{suffix}"

    admin = await asyncpg.connect(
        host=host, port=port, user="test", password="test", database="test_db"
    )
    await admin.execute(f'CREATE DATABASE "{database}"')
    await admin.close()

    yield BootstrapConfig(
        host=host,
        port=port,
        database=database,
        master_user="test",
        master_password="test",
        app_user=app_user,
        app_secret_arn="arn:aws:secretsmanager:eu-west-2:1:secret:app",
        aws_region="eu-west-2",
    )

    admin = await asyncpg.connect(
        host=host, port=port, user="test", password="test", database="test_db"
    )
    await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
    await admin.execute(f'DROP ROLE IF EXISTS "{app_user}"')
    await admin.close()


async def _master(config: BootstrapConfig) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=config.host,
        port=config.port,
        user=config.master_user,
        password=config.master_password,
        database=config.database,
    )


async def _as_app(config: BootstrapConfig, password: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=config.host,
        port=config.port,
        user=config.app_user,
        password=password,
        database=config.database,
    )


async def _ensure(config: BootstrapConfig, *, rotate: bool = False) -> str | None:
    conn = await _master(config)
    try:
        return await ensure_database(
            conn,
            database=config.database,
            app_user=config.app_user,
            master_user=config.master_user,
            rotate_password=rotate,
        )
    finally:
        await conn.close()


async def test_first_run_creates_login_that_owns_database_and_schema(
    bootstrap_config: BootstrapConfig,
) -> None:
    password = await _ensure(bootstrap_config)

    assert password is not None
    conn = await _as_app(bootstrap_config, password)
    try:
        db_owner = await conn.fetchval(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = $1",
            bootstrap_config.database,
        )
        schema_owner = await conn.fetchval(
            "SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
            "WHERE nspname = 'public'"
        )
        has_vector = await conn.fetchval(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        )
        is_superuser = await conn.fetchval(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        # The migration container runs DDL with this login
        await conn.execute("CREATE TABLE ddl_probe (id int, v vector(3))")
    finally:
        await conn.close()

    assert db_owner == bootstrap_config.app_user
    assert schema_owner == bootstrap_config.app_user
    assert has_vector == 1
    assert is_superuser is False


async def test_second_run_keeps_existing_password(
    bootstrap_config: BootstrapConfig,
) -> None:
    first = await _ensure(bootstrap_config)
    second = await _ensure(bootstrap_config)

    assert first is not None
    assert second is None
    conn = await _as_app(bootstrap_config, first)
    await conn.close()


async def test_rotate_replaces_password(bootstrap_config: BootstrapConfig) -> None:
    old = await _ensure(bootstrap_config)
    new = await _ensure(bootstrap_config, rotate=True)

    assert old is not None
    assert new is not None
    assert new != old
    with pytest.raises(asyncpg.InvalidPasswordError):
        await _as_app(bootstrap_config, old)
    conn = await _as_app(bootstrap_config, new)
    await conn.close()


async def test_run_writes_a_working_database_url_then_leaves_it_alone(
    bootstrap_config: BootstrapConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeSecretsClient({"DATABASE_URL": SECRET_PLACEHOLDER, "SECRET_KEY": "k"})
    monkeypatch.setattr(
        "app.cli.db_bootstrap.aioboto3.Session", lambda: FakeSession(client)
    )

    assert await db_bootstrap.run(bootstrap_config, rotate_password=False) == 0
    url = client.values["DATABASE_URL"]
    assert url.startswith(f"postgresql+asyncpg://{bootstrap_config.app_user}:")
    assert client.values["SECRET_KEY"] == "k"

    # The URL written into the secret really connects
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    assert await conn.fetchval("SELECT current_user") == bootstrap_config.app_user
    await conn.close()

    assert await db_bootstrap.run(bootstrap_config, rotate_password=False) == 0
    assert client.values["DATABASE_URL"] == url


async def test_run_with_existing_login_but_no_url_asks_for_rotation(
    bootstrap_config: BootstrapConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ensure(bootstrap_config)
    client = FakeSecretsClient({"DATABASE_URL": SECRET_PLACEHOLDER})
    monkeypatch.setattr(
        "app.cli.db_bootstrap.aioboto3.Session", lambda: FakeSession(client)
    )

    assert await db_bootstrap.run(bootstrap_config, rotate_password=False) == 1
    assert client.values["DATABASE_URL"] == SECRET_PLACEHOLDER

    assert await db_bootstrap.run(bootstrap_config, rotate_password=True) == 0
    assert client.values["DATABASE_URL"] != SECRET_PLACEHOLDER
