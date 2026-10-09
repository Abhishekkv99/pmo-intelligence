"""The node wrapper: every LLM node is timed, costed, time-limited, non-fatal."""

import asyncio
from typing import Any

import pytest

from app.ai.session import node as node_module
from app.ai.session.node import llm_node
from app.ai.session.state import SessionGraphState
from app.ai.structured import LLMUsage
from tests.unit.session_pipeline_helpers import context


def _state() -> SessionGraphState:
    return {"context": context()}


async def test_a_node_that_answers_returns_its_update_cost_and_success() -> None:
    async def work(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
        return {"summary": "A call."}, LLMUsage(input_tokens=1_000, output_tokens=200)

    update = await llm_node("summarise", work)(_state())

    assert update["summary"] == "A call."
    assert update["succeeded"] == ["summarise"]
    [cost] = update["cost_records"]
    assert cost["service"] == "azure_openai"
    assert cost["operation"] == "session_summarise"
    assert cost["input_tokens"] == 1_000
    assert cost["output_tokens"] == 200
    assert cost["amount_usd"] == pytest.approx(1_000 * 0.75e-6 + 200 * 4.5e-6)
    assert cost["duration_seconds"] >= 0
    assert "node_errors" not in update


async def test_a_node_that_raises_becomes_a_node_error() -> None:
    async def work(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
        raise RuntimeError("model unavailable")

    update = await llm_node("issues", work)(_state())

    assert update == {
        "node_errors": [
            {
                "node": "issues",
                "error": "RuntimeError: model unavailable",
                "duration_seconds": update["node_errors"][0]["duration_seconds"],
            }
        ]
    }


async def test_a_node_past_its_time_limit_is_stopped_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(node_module.settings, "session_node_timeout_seconds", 0.05)

    async def work(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
        await asyncio.sleep(5)
        return {}, LLMUsage(0, 0)

    update = await llm_node("actions", work)(_state())

    [error] = update["node_errors"]
    assert error["node"] == "actions"
    assert error["error"] == "Timed out after 0.05 s"
    assert error["duration_seconds"] < 2
    assert "succeeded" not in update


async def test_a_long_error_is_cut() -> None:
    async def work(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
        raise ValueError("x" * 2_000)

    update = await llm_node("classify", work)(_state())

    assert len(update["node_errors"][0]["error"]) == 500
