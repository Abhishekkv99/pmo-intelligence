"""Unit tests for the processing takeover sequence.

The lock itself is exercised against real Postgres in
``tests/integration/test_processing_ownership.py``; these pin down what the
takeover does around it: nothing until ownership is held, then the
registered sweeps, then the workers, then the registered re-queues - and
never give up.
"""

import asyncio
from collections.abc import Callable

import pytest

from app.services import processing_ownership
from app.services.processing_ownership import (
    TakeoverStep,
    hold_processing,
    register_takeover_requeue,
    register_takeover_sweep,
    take_over_processing,
)

MODULE = "app.services.processing_ownership"

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _empty_registries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the module-level takeover registries for every test."""
    monkeypatch.setattr(processing_ownership, "_takeover_sweeps", [])
    monkeypatch.setattr(processing_ownership, "_takeover_requeues", [])


def _step(calls: list[str], name: str, result: int = 0) -> TakeoverStep:
    async def step() -> int:
        calls.append(name)
        return result

    return step


def _failing(calls: list[str], name: str) -> TakeoverStep:
    async def step() -> int:
        calls.append(name)
        raise RuntimeError("boom")

    return step


def _register_recovery(calls: list[str]) -> None:
    register_takeover_sweep("a", _step(calls, "sweep_a"))
    register_takeover_sweep("b", _step(calls, "sweep_b"))
    register_takeover_requeue("a", _step(calls, "requeue_a"))
    register_takeover_requeue("b", _step(calls, "requeue_b"))


TAKEOVER = ["sweep_a", "sweep_b", "start", "requeue_a", "requeue_b"]


class _GatedOwnership:
    """An ownership whose acquire() returns only when the test opens the gate."""

    def __init__(self, failures: int = 0) -> None:
        self.gate = asyncio.Event()
        self.attempts = 0
        self._failures = failures

    async def acquire(self) -> None:
        self.attempts += 1
        if self.attempts <= self._failures:
            raise ConnectionError("database unreachable")
        await self.gate.wait()


class _RecordingQueue:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def start(self) -> None:
        self._calls.append("start")


async def _take_over(ownership: object, calls: list[str]) -> None:
    await take_over_processing(ownership, _RecordingQueue(calls))  # type: ignore[arg-type]


class TestTakeOverProcessing:
    async def test_nothing_runs_until_ownership_is_held(self) -> None:
        calls: list[str] = []
        _register_recovery(calls)
        ownership = _GatedOwnership()

        task = asyncio.create_task(_take_over(ownership, calls))
        for _ in range(5):
            await asyncio.sleep(0)
        # The other task still owns processing: no sweep, no workers.
        assert calls == []

        ownership.gate.set()
        await asyncio.wait_for(task, 5)

        assert calls == TAKEOVER

    async def test_a_failed_acquire_is_retried_not_abandoned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        ownership = _GatedOwnership(failures=2)
        ownership.gate.set()
        monkeypatch.setattr(processing_ownership, "ACQUIRE_RETRY_SECONDS", 0)

        await asyncio.wait_for(_take_over(ownership, calls), 5)

        assert ownership.attempts == 3
        assert calls == ["start"]

    async def test_a_failing_sweep_still_runs_the_rest(self) -> None:
        calls: list[str] = []
        register_takeover_sweep("bad", _failing(calls, "sweep_bad"))
        register_takeover_sweep("good", _step(calls, "sweep_good"))
        register_takeover_requeue("good", _step(calls, "requeue_good"))
        ownership = _GatedOwnership()
        ownership.gate.set()

        await _take_over(ownership, calls)

        assert calls == ["sweep_bad", "sweep_good", "start", "requeue_good"]

    async def test_a_failing_requeue_is_not_fatal(self) -> None:
        calls: list[str] = []
        register_takeover_requeue("bad", _failing(calls, "requeue_bad"))
        register_takeover_requeue("good", _step(calls, "requeue_good"))
        ownership = _GatedOwnership()
        ownership.gate.set()

        await _take_over(ownership, calls)

        assert calls == ["start", "requeue_bad", "requeue_good"]

    async def test_every_step_logs_its_count_zero_included(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A zero is logged too, so "ran and found nothing" can be told from
        # "never ran" (user decision 2026-10-10).
        calls: list[str] = []
        register_takeover_sweep("stuck_sessions", _step(calls, "sweep", result=3))
        register_takeover_requeue("pending", _step(calls, "requeue", result=0))
        ownership = _GatedOwnership()
        ownership.gate.set()

        with caplog.at_level("INFO", logger=MODULE):
            await _take_over(ownership, calls)

        assert "Takeover sweep stuck_sessions: 3 row(s)" in caplog.text
        assert "Takeover re-queue pending: 0 row(s)" in caplog.text

    async def test_steps_run_in_registration_order(self) -> None:
        calls: list[str] = []
        names = ["first", "second", "third"]
        steps: list[Callable[[], object]] = []
        for name in names:
            step = _step(calls, name)
            steps.append(step)
            register_takeover_sweep(name, step)
        ownership = _GatedOwnership()
        ownership.gate.set()

        await _take_over(ownership, calls)

        assert calls == [*names, "start"]


class _HeartbeatOwnership:
    """Holds the lock for ``holds`` heartbeats, then reports it lost once."""

    def __init__(self, holds: int) -> None:
        self.acquired = 0
        self._holds = holds
        self._checks = 0

    async def acquire(self) -> None:
        self.acquired += 1

    async def still_held(self) -> bool:
        self._checks += 1
        return self._checks != self._holds + 1


class _StoppableQueue(_RecordingQueue):
    async def stop(self) -> None:
        self._calls.append("stop")

    async def wait_for_stragglers(self) -> None:
        self._calls.append("wait")


class TestHoldProcessing:
    async def test_a_lost_lock_stops_the_queue_then_takes_over_again(self) -> None:
        calls: list[str] = []
        _register_recovery(calls)
        ownership = _HeartbeatOwnership(holds=2)

        task = asyncio.create_task(
            hold_processing(
                ownership,  # type: ignore[arg-type]
                _StoppableQueue(calls),  # type: ignore[arg-type]
                heartbeat_seconds=0,
            )
        )
        for _ in range(200):
            await asyncio.sleep(0)
            if calls.count("start") == 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls[:12] == [*TAKEOVER, "stop", "wait", *TAKEOVER]
        assert ownership.acquired == 2

    async def test_a_held_lock_keeps_the_queue_running(self) -> None:
        calls: list[str] = []
        _register_recovery(calls)
        ownership = _HeartbeatOwnership(holds=10_000)

        task = asyncio.create_task(
            hold_processing(
                ownership,  # type: ignore[arg-type]
                _StoppableQueue(calls),  # type: ignore[arg-type]
                heartbeat_seconds=0,
            )
        )
        for _ in range(50):
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert "stop" not in calls
        assert calls.count("start") == 1
        assert ownership.acquired == 1
