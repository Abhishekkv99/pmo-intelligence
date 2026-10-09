"""The session pipeline: one LangGraph run per transcribed call.

    attribute_roles → classify → summarise
        → [issues, relationship_engagement, client_signals, actions]
        → emit_signals

The four extraction nodes run in parallel; ``emit_signals`` waits for all of
them. Every LLM node is non-fatal (``llm_node``), so a run always reaches
``emit_signals``. The graph touches no database: the analysis service loads
the context and stores the result in one transaction.
"""

from dataclasses import dataclass
from functools import cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.ai.session import nodes
from app.ai.session.drafts import SessionAnalysis
from app.ai.session.emit import emit_signals
from app.ai.session.node import llm_node
from app.ai.session.state import SessionContext, SessionGraphState

EXTRACTION_NODES = (
    "issues",
    "relationship_engagement",
    "client_signals",
    "actions",
)
# A run is usable when the summary or at least one extraction succeeded;
# otherwise the session is failed so a person retries it.
USABLE_NODES = frozenset({"summarise", *EXTRACTION_NODES})


@dataclass(frozen=True)
class SessionRunResult:
    analysis: SessionAnalysis
    cost_records: list[dict[str, Any]]
    node_errors: list[dict[str, Any]]
    succeeded: list[str]

    @property
    def usable(self) -> bool:
        return bool(USABLE_NODES.intersection(self.succeeded))


def build_session_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(SessionGraphState)
    graph.add_node(
        "attribute_roles", llm_node("attribute_roles", nodes.attribute_roles)
    )
    graph.add_node("classify", llm_node("classify", nodes.classify_session))
    graph.add_node("summarise", llm_node("summarise", nodes.summarise_session))
    graph.add_node("issues", llm_node("issues", nodes.extract_issues))
    graph.add_node(
        "relationship_engagement",
        llm_node("relationship_engagement", nodes.extract_relationship_engagement),
    )
    graph.add_node(
        "client_signals", llm_node("client_signals", nodes.extract_client_signals)
    )
    graph.add_node("actions", llm_node("actions", nodes.extract_actions))
    graph.add_node("emit_signals", emit_signals)

    graph.add_edge(START, "attribute_roles")
    graph.add_edge("attribute_roles", "classify")
    graph.add_edge("classify", "summarise")
    for name in EXTRACTION_NODES:
        graph.add_edge("summarise", name)
    graph.add_edge(list(EXTRACTION_NODES), "emit_signals")
    graph.add_edge("emit_signals", END)
    return graph.compile()


@cache
def _session_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    return build_session_graph()


async def run_session_pipeline(context: SessionContext) -> SessionRunResult:
    final = await _session_graph().ainvoke(
        {"context": context, "cost_records": [], "node_errors": [], "succeeded": []}
    )
    return SessionRunResult(
        analysis=final.get("analysis") or SessionAnalysis(),
        cost_records=list(final.get("cost_records", [])),
        node_errors=list(final.get("node_errors", [])),
        succeeded=list(final.get("succeeded", [])),
    )
