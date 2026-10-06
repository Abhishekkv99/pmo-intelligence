"""Shared factory for Azure OpenAI LLM and embedding instances.

Both builders are cached: the settings they read are fixed for the life of the
process, and every caller only derives runnables from the instance
(``with_structured_output``, ``ainvoke``), so one client per reasoning effort
serves the whole pipeline instead of ~15 fresh instances per pipeline run.

Both set a request timeout. langchain-openai passes ``timeout=None`` to the
OpenAI client unless one is given, which disables the client's own default,
so without it a connection that dies silently is awaited forever. On
2026-10-05 one such folder-name call stopped the periodic scanner for 11
hours.
"""

import functools

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from pydantic import SecretStr

from app.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@functools.cache
def build_chat_llm(
    reasoning_effort: str = "medium",
) -> AzureChatOpenAI:
    """Create an AzureChatOpenAI instance with the given parameters.

    Note: gpt-5.4-mini on Azure does not support custom temperature
    (only default 1 is allowed), so temperature is not configurable.
    """
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        api_key=SecretStr(settings.azure_openai_api_key),
        api_version=settings.azure_openai_api_version,
        reasoning_effort=reasoning_effort,
        timeout=settings.azure_openai_timeout_seconds,
    )


@functools.cache
def build_embeddings() -> AzureOpenAIEmbeddings:
    """Create an AzureOpenAIEmbeddings instance for text-embedding-3-small."""
    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_embedding_deployment,
        api_key=SecretStr(settings.azure_openai_api_key),
        api_version=settings.azure_openai_api_version,
        timeout=settings.azure_openai_timeout_seconds,
    )
