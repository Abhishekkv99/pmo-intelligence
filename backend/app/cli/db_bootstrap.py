"""One-off database bootstrap for a deployed environment.

Runs as an ECS task inside the VPC (RDS is private), connected as the RDS
master user:

1. creates the ``vector`` extension;
2. creates the application login (``pmo_app``) with a random password, or
   keeps an existing one unless ``--rotate-password`` is given;
3. makes it the owner of the database and its ``public`` schema, so the
   migration init container can run DDL with the same URL;
4. writes ``DATABASE_URL`` for that login into the app secret, after checking
   the new credentials connect.

Re-running is safe: an existing login keeps its password and the secret is left
alone. No password or URL is ever logged.

Usage (inside the task): ``python -m app.cli.db_bootstrap [--rotate-password]``
"""

import argparse
import asyncio
import json
import logging
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import aioboto3
import asyncpg

logger = logging.getLogger("db_bootstrap")

# What the Terraform-created app secret holds until this script has run
SECRET_PLACEHOLDER = "SET_BY_DB_BOOTSTRAP"
PASSWORD_BYTES = 32
CONNECT_TIMEOUT_SECONDS = 30


class SecretsClient(Protocol):
    """The two Secrets Manager calls the bootstrap makes (parameter names are
    the AWS API's)."""

    async def get_secret_value(
        self,
        *,
        SecretId: str,  # noqa: N803
    ) -> dict[str, Any]: ...

    async def put_secret_value(
        self,
        *,
        SecretId: str,  # noqa: N803
        SecretString: str,  # noqa: N803
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BootstrapConfig:
    host: str
    port: int
    database: str
    master_user: str
    master_password: str
    app_user: str
    app_secret_arn: str
    aws_region: str
    # asyncpg sslmode; RDS PostgreSQL 16 requires TLS and "prefer" negotiates it
    ssl: str = "prefer"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "BootstrapConfig":
        source = os.environ if env is None else env
        required = [
            "DB_HOST",
            "DB_NAME",
            "DB_MASTER_USERNAME",
            "DB_MASTER_PASSWORD",
            "APP_SECRET_ARN",
            "AWS_REGION",
        ]
        missing = [name for name in required if not source.get(name)]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
        return cls(
            host=source["DB_HOST"],
            port=int(source.get("DB_PORT", "5432")),
            database=source["DB_NAME"],
            master_user=source["DB_MASTER_USERNAME"],
            master_password=source["DB_MASTER_PASSWORD"],
            app_user=source.get("APP_DB_USER", "pmo_app"),
            app_secret_arn=source["APP_SECRET_ARN"],
            aws_region=source["AWS_REGION"],
            ssl=source.get("DB_SSL", "prefer"),
        )


def generate_password() -> str:
    """URL-safe random password (no quoting surprises in SQL or URLs)."""
    return secrets.token_urlsafe(PASSWORD_BYTES)


def build_database_url(
    *, user: str, password: str, host: str, port: int, database: str
) -> str:
    """SQLAlchemy asyncpg URL with the user and password percent-encoded."""
    return (
        f"postgresql+asyncpg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


async def _execute_formatted(
    conn: asyncpg.Connection, template: str, *args: str
) -> None:
    """Run DDL built by the server's format(), so identifiers (%I) and
    literals (%L) are quoted by PostgreSQL itself; DDL takes no bind params."""
    statement = await conn.fetchval(
        "SELECT format($1, VARIADIC $2::text[])", template, list(args)
    )
    await conn.execute(statement)


async def ensure_database(
    conn: asyncpg.Connection,
    *,
    database: str,
    app_user: str,
    master_user: str,
    rotate_password: bool,
) -> str | None:
    """Bring the database to the expected state.

    Returns the new password when the login was created or rotated, otherwise
    None (an existing login keeps its password).
    """
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    logger.info("vector extension present")

    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", app_user)
    password: str | None = None
    if not exists:
        password = generate_password()
        await _execute_formatted(
            conn, "CREATE ROLE %I LOGIN PASSWORD %L", app_user, password
        )
        logger.info("created login %s", app_user)
    elif rotate_password:
        password = generate_password()
        await _execute_formatted(conn, "ALTER ROLE %I PASSWORD %L", app_user, password)
        logger.info("rotated the password of %s", app_user)
    else:
        logger.info("login %s exists; password kept", app_user)

    # Handing ownership to a role needs membership in it (on RDS the master
    # user is not a superuser)
    await _execute_formatted(conn, "GRANT %I TO %I", app_user, master_user)
    await _execute_formatted(conn, "ALTER DATABASE %I OWNER TO %I", database, app_user)
    await _execute_formatted(conn, "ALTER SCHEMA public OWNER TO %I", app_user)
    logger.info("%s owns database %s and its public schema", app_user, database)
    return password


async def verify_login(config: BootstrapConfig, password: str) -> None:
    """Connect with the new credentials before anything relies on them."""
    conn = await asyncpg.connect(
        host=config.host,
        port=config.port,
        user=config.app_user,
        password=password,
        database=config.database,
        ssl=config.ssl,
        timeout=CONNECT_TIMEOUT_SECONDS,
    )
    try:
        user = await conn.fetchval("SELECT current_user")
        if user != config.app_user:
            raise RuntimeError(f"Connected as {user}, expected {config.app_user}")
    finally:
        await conn.close()
    logger.info("verified that %s can connect", config.app_user)


async def read_database_url(client: SecretsClient, secret_arn: str) -> str:
    response = await client.get_secret_value(SecretId=secret_arn)
    values: dict[str, Any] = json.loads(response["SecretString"])
    return str(values.get("DATABASE_URL", ""))


async def store_database_url(client: SecretsClient, secret_arn: str, url: str) -> None:
    """Replace DATABASE_URL in the app secret, keeping every other key."""
    response = await client.get_secret_value(SecretId=secret_arn)
    values: dict[str, Any] = json.loads(response["SecretString"])
    values["DATABASE_URL"] = url
    await client.put_secret_value(SecretId=secret_arn, SecretString=json.dumps(values))
    logger.info("wrote DATABASE_URL into the app secret")


def secret_needs_url(current_url: str) -> bool:
    """True when the secret has no usable DATABASE_URL yet."""
    return not current_url or current_url == SECRET_PLACEHOLDER


async def run(config: BootstrapConfig, *, rotate_password: bool) -> int:
    conn = await asyncpg.connect(
        host=config.host,
        port=config.port,
        user=config.master_user,
        password=config.master_password,
        database=config.database,
        ssl=config.ssl,
        timeout=CONNECT_TIMEOUT_SECONDS,
    )
    try:
        password = await ensure_database(
            conn,
            database=config.database,
            app_user=config.app_user,
            master_user=config.master_user,
            rotate_password=rotate_password,
        )
    finally:
        await conn.close()

    session = aioboto3.Session()
    async with session.client(
        "secretsmanager", region_name=config.aws_region
    ) as client:
        if password is None:
            if secret_needs_url(await read_database_url(client, config.app_secret_arn)):
                logger.error(
                    "%s exists but the app secret has no DATABASE_URL; "
                    "its password is unknown, so run again with --rotate-password",
                    config.app_user,
                )
                return 1
            logger.info("app secret already holds DATABASE_URL; left unchanged")
            return 0

        await verify_login(config, password)
        url = build_database_url(
            user=config.app_user,
            password=password,
            host=config.host,
            port=config.port,
            database=config.database,
        )
        await store_database_url(client, config.app_secret_arn, url)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rotate-password",
        action="store_true",
        help="give the app login a new password and rewrite DATABASE_URL",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    try:
        config = BootstrapConfig.from_env()
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    return asyncio.run(run(config, rotate_password=args.rotate_password))


if __name__ == "__main__":
    sys.exit(main())
