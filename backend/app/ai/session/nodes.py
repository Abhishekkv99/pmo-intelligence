"""The session pipeline's LLM nodes: one structured-output call each.

Each returns its state update and the call's token usage; ``llm_node`` makes
it non-fatal, timed and costed. Every node after ``attribute_roles`` reads
the transcript with the roles it found, when it found them.
"""

from typing import Any

from pydantic import BaseModel

from app.ai.session.prompts import (
    actions,
    classify,
    client_signals,
    issues,
    relationship_engagement,
    roles,
    summarise,
)
from app.ai.session.prompts.common import render_transcript
from app.ai.session.schemas import (
    ActionsResult,
    ClassificationResult,
    IssuesResult,
    RoleAttributionResult,
    SignalsResult,
    SummaryResult,
)
from app.ai.session.state import SessionContext, SessionGraphState
from app.ai.structured import LLMUsage, invoke_structured
from app.config import settings


async def _ask[ModelT: BaseModel](
    schema: type[ModelT], system: str, user: str
) -> tuple[ModelT, LLMUsage]:
    return await invoke_structured(
        schema, system, user, reasoning_effort=settings.session_reasoning_effort
    )


def _transcript(state: SessionGraphState) -> tuple[SessionContext, str]:
    context = state["context"]
    return context, render_transcript(context, state.get("speakers"))


async def attribute_roles(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
    context = state["context"]
    result, usage = await _ask(
        RoleAttributionResult,
        roles.SYSTEM,
        roles.build_user(context, render_transcript(context)),
    )
    return {"speakers": result.speakers}, usage


async def classify_session(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        ClassificationResult, classify.SYSTEM, classify.build_user(context, transcript)
    )
    return {
        "session_class": result.session_class.value,
        "project_phase": result.project_phase,
    }, usage


async def summarise_session(
    state: SessionGraphState,
) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        SummaryResult, summarise.SYSTEM, summarise.build_user(context, transcript)
    )
    return {"summary": result.summary}, usage


async def extract_issues(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        IssuesResult, issues.SYSTEM, issues.build_user(context, transcript)
    )
    return {"issues": result.issues}, usage


async def extract_relationship_engagement(
    state: SessionGraphState,
) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        SignalsResult,
        relationship_engagement.SYSTEM,
        relationship_engagement.build_user(context, transcript),
    )
    return {"relationship_signals": result.signals}, usage


async def extract_client_signals(
    state: SessionGraphState,
) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        SignalsResult,
        client_signals.SYSTEM,
        client_signals.build_user(context, transcript),
    )
    return {"client_signals": result.signals}, usage


async def extract_actions(state: SessionGraphState) -> tuple[dict[str, Any], LLMUsage]:
    context, transcript = _transcript(state)
    result, usage = await _ask(
        ActionsResult, actions.SYSTEM, actions.build_user(context, transcript)
    )
    return {"actions": result.actions, "closed_actions": result.closed}, usage
