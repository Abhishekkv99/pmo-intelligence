"""Integration test fixtures — testcontainers PostgreSQL + pgvector."""

import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.db.repositories.user_repo import UserRepository
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.enums import Role
from app.models.user import User
from app.rate_limiter import limiter
from app.services.auth_service import AuthService
from app.services.processing_queue import ProcessingQueue, set_processing_queue
from app.utils.exceptions import AuthenticationError

# Windows Docker Desktop uses a different named pipe than the default.
# Set DOCKER_HOST so the Docker SDK (used by testcontainers) can find it.
if os.name == "nt" and not os.environ.get("DOCKER_HOST"):
    os.environ["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Start a PostgreSQL container with pgvector for the entire test session."""
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_db",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Build the async database URL from the running container."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://test:test@{host}:{port}/test_db"


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncGenerator:
    """Create a session-scoped async engine and set up all tables once."""
    test_engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,
    )

    # Create pgvector extension + all tables
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """Start every test with a fresh rate-limit window.

    The limiter's in-memory storage is process-global and keyed by client IP,
    and every ASGI test client shares one IP, so the fourth ``POST
    /auth/register`` in a minute — across tests, not within one — answers 429
    (3/minute) for a reason unrelated to the test. The unit suite resets the
    same storage around its rate-limit tests.
    """
    limiter.reset()


@pytest.fixture(autouse=True)
def _fresh_processing_queue() -> Generator[ProcessingQueue]:
    """Give every test its own, never-started processing queue.

    The routes enqueue into a process-wide singleton. A fresh instance per
    test means a test can assert exactly what it enqueued (``snapshot()``)
    and that nothing leaks between tests; never starting it means no worker
    ever runs a job against a mocked session.
    """
    queue = ProcessingQueue(concurrency=1)
    set_processing_queue(queue)
    yield queue
    set_processing_queue(None)


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession]:
    """Per-test database session with savepoint rollback for isolation."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


async def _create_user(
    db_session: AsyncSession,
    *,
    email: str,
    full_name: str,
    role: Role | None,
) -> User:
    """Create a user row with an explicit role (``None``: no access yet).

    Goes through the repository rather than ``register``, so the bootstrap
    rule is not applied — the role is whatever the caller says it is.
    """
    return await UserRepository(db_session).create(
        email=email,
        hashed_password=AuthService._hash_password("TestPass123"),
        full_name=full_name,
        role=role.value if role else None,
    )


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """A placement specialist — the caller behind ``authenticated_client``."""
    return await _create_user(
        db_session,
        email="testuser@example.com",
        full_name="Test User",
        role=Role.PS,
    )


@pytest.fixture
async def test_manager(db_session: AsyncSession) -> User:
    """A PMO manager: reads every placement."""
    return await _create_user(
        db_session,
        email="manager@example.com",
        full_name="Manager User",
        role=Role.PMO_MANAGER,
    )


@pytest.fixture
async def test_user_no_role(db_session: AsyncSession) -> User:
    """A signed-in user with no role yet: reads nothing."""
    return await _create_user(
        db_session,
        email="norole@example.com",
        full_name="No Role User",
        role=None,
    )


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Generate a JWT access token for the test user."""
    return AuthService.create_access_token(test_user.id)


def _install_overrides(db_session: AsyncSession) -> None:
    """Point ``get_db`` and ``get_current_user`` at the test session.

    The overrides are app-global, so the caller is resolved from the bearer
    token on every request — exactly as production does — rather than closed
    over one fixture's user. That lets two clients signed in as different
    users share a test; with a per-fixture closure, whichever client was
    created last would answer for both.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    async def _override_get_current_user(request: Request) -> User:
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip()
        user = await db_session.get(User, AuthService.decode_access_token(token))
        if user is None:
            raise AuthenticationError("User not found")
        # Production get_current_user loads the user row on every request, so
        # its attributes are always loaded. Mirror that here: a test may have
        # expired the shared session (expire_all()), and the entitlement
        # dependencies read the role — an expired attribute on a session-bound
        # object would lazy-load outside the async context and raise
        # MissingGreenlet.
        await db_session.refresh(user)
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user


@asynccontextmanager
async def _client_as(
    db_session: AsyncSession, token: str
) -> AsyncGenerator[AsyncClient]:
    """An HTTP test client whose every request carries ``token``."""
    _install_overrides(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(
    db_session: AsyncSession,
    test_user: User,
    auth_token: str,
) -> AsyncGenerator[AsyncClient]:
    """HTTP test client signed in as ``test_user`` (placement specialist)."""
    async with _client_as(db_session, auth_token) as ac:
        yield ac


@pytest.fixture
async def manager_client(
    db_session: AsyncSession,
    test_manager: User,
) -> AsyncGenerator[AsyncClient]:
    """HTTP test client signed in as ``test_manager`` (every placement)."""
    token = AuthService.create_access_token(test_manager.id)
    async with _client_as(db_session, token) as ac:
        yield ac


@pytest.fixture
async def no_role_client(
    db_session: AsyncSession,
    test_user_no_role: User,
) -> AsyncGenerator[AsyncClient]:
    """HTTP test client signed in as ``test_user_no_role``."""
    token = AuthService.create_access_token(test_user_no_role.id)
    async with _client_as(db_session, token) as ac:
        yield ac


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Unauthenticated HTTP test client for testing public endpoints and 401s."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
