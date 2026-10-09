"""The one wrapper every LLM node of the session pipeline runs inside.

It times the node, costs its call, and stops it after
``SESSION_NODE_TIMEOUT_SECONDS``. Any failure, a timeout included, becomes a
``node_errors`` entry and the graph carries on with what it has: no node can
fail the run. A node that returned is listed in ``succeeded``, which decides
whether the run produced anything usable.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.ai.session.state import SessionGraphState
from app.ai.structured import LLMUsage
from app.config import settings
from app.services.cost_tracker import calculate_llm_cost

logger = logging.getLogger(__name__)

# A node's work: the state update it produces and the call's token usage.
NodeWork = Callable[[SessionGraphState], Awaitable[tuple[dict[str, Any], LLMUsage]]]


class Node(Protocol):
    """A graph node, typed as LangGraph's ``add_node`` expects (``state``)."""

    def __call__(self, state: SessionGraphState) -> Awaitable[dict[str, Any]]: ...


ERROR_TEXT_LIMIT = 500


def node_error(name: str, error: str, duration_seconds: float) -> dict[str, Any]:
    return {
        "node": name,
        "error": error[:ERROR_TEXT_LIMIT],
        "duration_seconds": round(duration_seconds, 3),
    }


def llm_node(name: str, work: NodeWork) -> Node:
    """``work`` as a non-fatal, timed, costed graph node called ``name``."""

    async def run(state: SessionGraphState) -> dict[str, Any]:
        limit = settings.session_node_timeout_seconds
        started = time.perf_counter()
        try:
            async with asyncio.timeout(limit):
                update, usage = await work(state)
        except TimeoutError:
            elapsed = time.perf_counter() - started
            logger.warning("Session node %s timed out after %s s", name, limit)
            return {
                "node_errors": [node_error(name, f"Timed out after {limit} s", elapsed)]
            }
        except Exception as exc:
            elapsed = time.perf_counter() - started
            logger.exception("Session node %s failed", name)
            return {
                "node_errors": [
                    node_error(name, f"{type(exc).__name__}: {exc}", elapsed)
                ]
            }
        elapsed = time.perf_counter() - started
        cost = {
            "service": "azure_openai",
            "operation": f"session_{name}",
            "amount_usd": calculate_llm_cost(usage.input_tokens, usage.output_tokens),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "model": settings.azure_openai_deployment,
            "duration_seconds": elapsed,
        }
        logger.info(
            "Session node %s took %.1f s (%d in, %d out)",
            name,
            elapsed,
            usage.input_tokens,
            usage.output_tokens,
        )
        return {**update, "cost_records": [cost], "succeeded": [name]}

    return run
