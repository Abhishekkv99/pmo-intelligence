"""Unit tests for the database bootstrap CLI (no database needed)."""

import json
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

from app.cli import db_bootstrap
from app.cli.db_bootstrap import (
    SECRET_PLACEHOLDER,
    BootstrapConfig,
    build_database_url,
    generate_password,
    read_database_url,
    secret_needs_url,
    store_database_url,
)

FULL_ENV = {
    "DB_HOST": "db.internal",
    "DB_NAME": "pmo_intelligence",
    "DB_MASTER_USERNAME": "postgres",
    "DB_MASTER_PASSWORD": "master-secret",
    "APP_SECRET_ARN": "arn:aws:secretsmanager:eu-west-2:1:secret:app",
    "AWS_REGION": "eu-west-2",
}


class FakeSecretsClient:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        self.puts: list[str] = []

    async def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:  # noqa: N803
        return {"SecretString": json.dumps(self.values)}

    async def put_secret_value(
        self,
        *,
        SecretId: str,  # noqa: N803
        SecretString: str,  # noqa: N803
    ) -> dict[str, Any]:
        self.puts.append(SecretString)
        self.values = json.loads(SecretString)
        return {}


def test_from_env_with_required_values_applies_defaults() -> None:
    config = BootstrapConfig.from_env(FULL_ENV)

    assert config.host == "db.internal"
    assert config.port == 5432
    assert config.app_user == "pmo_app"
    assert config.ssl == "prefer"


def test_from_env_reads_optional_overrides() -> None:
    env = {
        **FULL_ENV,
        "DB_PORT": "6543",
        "APP_DB_USER": "other_app",
        "DB_SSL": "require",
    }

    config = BootstrapConfig.from_env(env)

    assert config.port == 6543
    assert config.app_user == "other_app"
    assert config.ssl == "require"


def test_from_env_missing_values_lists_every_missing_name() -> None:
    env = {k: v for k, v in FULL_ENV.items() if k not in {"DB_HOST", "APP_SECRET_ARN"}}

    with pytest.raises(ValueError, match="DB_HOST") as exc_info:
        BootstrapConfig.from_env(env)

    assert "APP_SECRET_ARN" in str(exc_info.value)


def test_build_database_url_percent_encodes_credentials() -> None:
    url = build_database_url(
        user="pmo_app", password="p@ss/w:rd%", host="db", port=5432, database="pmo"
    )

    parts = urlsplit(url)
    assert url.startswith("postgresql+asyncpg://")
    assert parts.hostname == "db"
    assert parts.port == 5432
    assert parts.path == "/pmo"
    assert unquote(parts.password or "") == "p@ss/w:rd%"


def test_generate_password_is_long_url_safe_and_unique() -> None:
    passwords = {generate_password() for _ in range(20)}

    assert len(passwords) == 20
    for password in passwords:
        assert len(password) >= 40
        assert set(password) <= set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("", True),
        (SECRET_PLACEHOLDER, True),
        ("postgresql+asyncpg://pmo_app:x@db:5432/pmo", False),
    ],
)
def test_secret_needs_url(current: str, expected: bool) -> None:
    assert secret_needs_url(current) is expected


async def test_store_database_url_replaces_only_database_url() -> None:
    client = FakeSecretsClient(
        {
            "DATABASE_URL": SECRET_PLACEHOLDER,
            "SECRET_KEY": "keep-me",
            "AZURE_TENANT_ID": "t",
        }
    )

    await store_database_url(client, "arn", "postgresql+asyncpg://u:p@h:5432/d")

    assert client.values == {
        "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/d",
        "SECRET_KEY": "keep-me",
        "AZURE_TENANT_ID": "t",
    }
    assert len(client.puts) == 1


async def test_read_database_url_missing_key_returns_empty() -> None:
    client = FakeSecretsClient({"SECRET_KEY": "x"})

    assert await read_database_url(client, "arn") == ""


def test_main_without_environment_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in FULL_ENV:
        monkeypatch.delenv(name, raising=False)

    assert db_bootstrap.main([]) == 2
