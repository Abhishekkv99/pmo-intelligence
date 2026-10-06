"""A statement that outlives asyncpg's command_timeout raises instead of hanging.

On 2026-09-24 the RDS instance ran out of memory and restarted, and three
processing jobs froze mid-write for good because nothing bounded a
statement. The app engine now passes ``command_timeout`` to asyncpg
(``app/db/session.py``); this proves the argument takes effect through
SQLAlchemy against real Postgres, with a short timeout and a longer sleep.
"""

import asyncio
import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def test_a_statement_past_the_command_timeout_raises(database_url: str) -> None:
    engine = create_async_engine(
        database_url, poolclass=NullPool, connect_args={"command_timeout": 0.5}
    )
    try:
        started = time.monotonic()
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT pg_sleep(5)"))
        assert time.monotonic() - started < 4
    finally:
        await engine.dispose()
