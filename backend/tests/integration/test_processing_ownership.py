"""The processing-ownership advisory lock admits one owner at a time (real DB).

During an ECS rolling deploy the old and new backend tasks are both alive
for about six minutes. Each builds a ``ProcessingOwnership`` over the same
database; the new one must wait until the old one lets go - by releasing it
on a clean shutdown, or by its connection dying with the process.

Every test uses its own random lock key, so they cannot see each other (or a
lock held by anything else using the default key).
"""

import asyncio
import random

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.processing_ownership import ProcessingOwnership


def _key() -> int:
    return random.randint(1, 2**62)


async def _still_waiting(task: asyncio.Task[None], seconds: float = 0.4) -> bool:
    done, _ = await asyncio.wait({task}, timeout=seconds)
    return not done


async def test_a_second_owner_waits_until_the_first_releases(
    engine: AsyncEngine,
) -> None:
    key = _key()
    first = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    second = ProcessingOwnership(engine, key=key, poll_seconds=0.05)

    await first.acquire()
    waiting = asyncio.create_task(second.acquire())
    try:
        assert await _still_waiting(waiting)
        assert not second.is_held

        await first.release()
        await asyncio.wait_for(waiting, 5)

        assert second.is_held
    finally:
        waiting.cancel()
        await first.release()
        await second.release()


async def test_a_dead_owners_lock_is_released_with_its_connection(
    engine: AsyncEngine,
) -> None:
    """A killed task never calls release(); its socket closing must be enough."""
    key = _key()
    first = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    second = ProcessingOwnership(engine, key=key, poll_seconds=0.05)

    await first.acquire()
    waiting = asyncio.create_task(second.acquire())
    try:
        assert await _still_waiting(waiting)

        # Simulate the process dying: drop the connection without unlocking.
        connection = first._connection
        assert connection is not None
        first._connection = None
        await connection.close()

        await asyncio.wait_for(waiting, 5)
        assert second.is_held
    finally:
        waiting.cancel()
        await second.release()


async def test_release_is_idempotent_and_the_lock_can_be_taken_again(
    engine: AsyncEngine,
) -> None:
    key = _key()
    owner = ProcessingOwnership(engine, key=key, poll_seconds=0.05)

    await owner.acquire()
    await owner.acquire()  # already held: a no-op, not a second lock
    await owner.release()
    await owner.release()
    assert not owner.is_held

    again = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    await asyncio.wait_for(again.acquire(), 5)
    assert again.is_held
    await again.release()


async def test_an_acquire_cancelled_while_waiting_leaves_nothing_held(
    engine: AsyncEngine,
) -> None:
    """Shutdown cancels a takeover that is still waiting; the lock must stay free."""
    key = _key()
    first = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    second = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    await first.acquire()

    waiting = asyncio.create_task(second.acquire())
    assert await _still_waiting(waiting)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert not second.is_held

    await first.release()
    third = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    await asyncio.wait_for(third.acquire(), 5)
    await third.release()


async def test_still_held_confirms_a_held_lock(engine: AsyncEngine) -> None:
    owner = ProcessingOwnership(engine, key=_key(), poll_seconds=0.05)
    assert not await owner.still_held()  # never acquired

    await owner.acquire()
    try:
        assert await owner.still_held()
        assert await owner.still_held()  # checking does not disturb the lock
    finally:
        await owner.release()


async def test_a_lock_lost_with_its_connection_is_noticed_and_can_be_retaken(
    engine: AsyncEngine,
) -> None:
    """The 2026-09-23 failure: a DB blip kills the lock's connection server-side.

    The owner must notice on its next check rather than go on processing, and
    another task must be able to take the lock meanwhile.
    """
    key = _key()
    first = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    second = ProcessingOwnership(engine, key=key, poll_seconds=0.05)
    await first.acquire()
    connection = first._connection
    assert connection is not None
    pid = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()

    async with engine.connect() as admin:
        await admin.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        await admin.commit()

    try:
        # Postgres released the lock with the connection, so another task
        # can take it at once - which is why the first must stop.
        await asyncio.wait_for(second.acquire(), 5)
        assert not await first.still_held()
        assert not first.is_held
    finally:
        await second.release()

    # Once the other owner lets go, the first takes it back from scratch.
    await asyncio.wait_for(first.acquire(), 5)
    assert await first.still_held()
    await first.release()
