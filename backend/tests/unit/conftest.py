"""Unit test fixtures — no database, no Docker."""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.processing_queue import ProcessingQueue, set_processing_queue


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Simple HTTP client without DB injection (for unit tests)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


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
