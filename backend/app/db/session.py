from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Longest a single SQL statement may run before asyncpg raises TimeoutError.
# Without it, a statement in flight when the database dies waits forever:
# on 2026-09-24 the RDS instance ran out of memory and restarted, and three
# processing jobs froze mid-write for good, holding their connections and
# their worker slots. No query in the app comes close to this; it only
# turns a dead connection into an error the job can fail on.
DB_COMMAND_TIMEOUT_SECONDS = 60

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_pre_ping=True,
    connect_args={"command_timeout": DB_COMMAND_TIMEOUT_SECONDS},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
