"""Unit tests for the shared LLM factory."""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from langchain_openai import AzureChatOpenAI
from openai import AsyncAzureOpenAI

from app.ai.llm_factory import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    build_chat_llm,
    build_embedding_client,
)


@pytest.fixture(autouse=True)
def _fresh_factory_caches() -> Iterator[None]:
    """Both builders are cached for the life of the process; tests patch
    settings per case, so the caches are cleared around each one."""
    build_chat_llm.cache_clear()
    build_embedding_client.cache_clear()
    yield
    build_chat_llm.cache_clear()
    build_embedding_client.cache_clear()


class TestBuildChatLLM:
    @patch("app.ai.llm_factory.settings")
    def test_returns_azure_chat_instance(self, mock_settings: MagicMock) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "gpt-52"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"

        llm = build_chat_llm()

        assert isinstance(llm, AzureChatOpenAI)

    @patch("app.ai.llm_factory.settings")
    def test_reasoning_effort_set_on_instance(self, mock_settings: MagicMock) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "gpt-52"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"

        llm = build_chat_llm(reasoning_effort="low")

        assert llm.reasoning_effort == "low"

    @patch("app.ai.llm_factory.settings")
    def test_uses_azure_deployment_from_settings(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "my-gpt-deployment"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"

        llm = build_chat_llm()

        assert llm.deployment_name == "my-gpt-deployment"

    @patch("app.ai.llm_factory.settings")
    def test_same_effort_returns_the_same_instance(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "gpt-52"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"

        assert build_chat_llm() is build_chat_llm()
        assert build_chat_llm("low") is build_chat_llm("low")

    @patch("app.ai.llm_factory.settings")
    def test_different_effort_returns_a_different_instance(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "gpt-52"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"

        assert build_chat_llm("low") is not build_chat_llm("high")

    @patch("app.ai.llm_factory.settings")
    def test_requests_time_out_after_the_configured_seconds(
        self, mock_settings: MagicMock
    ) -> None:
        """langchain-openai's default is no timeout at all; a dead connection
        held the periodic scanner for 11 hours on 2026-10-05."""
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment = "gpt-52"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"
        mock_settings.azure_openai_timeout_seconds = 123

        llm = build_chat_llm()

        assert llm.request_timeout == 123
        # It reaches the client that makes the call, not just the wrapper
        assert llm.root_async_client.timeout == 123


class TestBuildEmbeddingClient:
    @patch("app.ai.llm_factory.settings")
    def test_returns_an_azure_client_for_the_endpoint(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"
        mock_settings.azure_openai_timeout_seconds = 300

        client = build_embedding_client()

        assert isinstance(client, AsyncAzureOpenAI)
        assert str(client.base_url).startswith("https://test.openai.azure.com/")
        assert client.api_key == "test-key"

    @patch("app.ai.llm_factory.settings")
    def test_the_client_is_cached(self, mock_settings: MagicMock) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"
        mock_settings.azure_openai_timeout_seconds = 300

        assert build_embedding_client() is build_embedding_client()

    @patch("app.ai.llm_factory.settings")
    def test_requests_time_out_after_the_configured_seconds(
        self, mock_settings: MagicMock
    ) -> None:
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_api_version = "2025-04-01-preview"
        mock_settings.azure_openai_timeout_seconds = 123

        assert build_embedding_client().timeout == 123


class TestConstants:
    def test_embedding_model_name(self) -> None:
        assert EMBEDDING_MODEL == "text-embedding-3-small"

    def test_embedding_dimensions(self) -> None:
        assert EMBEDDING_DIMENSIONS == 1536
