"""Unit tests for cost tracking calculations."""

import pytest

from app.config import settings
from app.services.cost_tracker import (
    GPT54_MINI_INPUT_COST_PER_TOKEN,
    GPT54_MINI_OUTPUT_COST_PER_TOKEN,
    calculate_assemblyai_cost,
    calculate_embedding_cost,
    calculate_llm_cost,
)


class TestCalculateLLMCost:
    def test_typical_usage(self) -> None:
        # 1000 input + 500 output tokens
        cost = calculate_llm_cost(1000, 500)
        expected = (
            1000 * GPT54_MINI_INPUT_COST_PER_TOKEN
            + 500 * GPT54_MINI_OUTPUT_COST_PER_TOKEN
        )
        assert cost == expected
        # $0.75/M * 1000 = $0.00075 input + $4.50/M * 500 = $0.00225 output = $0.003
        assert abs(cost - 0.003) < 1e-10

    def test_zero_tokens(self) -> None:
        cost = calculate_llm_cost(0, 0)
        assert cost == 0.0

    def test_large_token_count(self) -> None:
        # 1M input + 1M output
        cost = calculate_llm_cost(1_000_000, 1_000_000)
        assert abs(cost - 5.25) < 1e-10  # $0.75 + $4.50


class TestCalculateEmbeddingCost:
    def test_typical_usage(self) -> None:
        # 1M tokens at $0.02/M = $0.02
        cost = calculate_embedding_cost(1_000_000)
        assert abs(cost - 0.02) < 1e-10

    def test_small_token_count(self) -> None:
        cost = calculate_embedding_cost(100)
        assert cost > 0
        assert cost < 0.001


class TestCalculateAssemblyAICost:
    def test_one_hour_with_diarization(self) -> None:
        # Universal-3.5 Pro $0.21/hr plus diarization $0.02/hr
        cost = calculate_assemblyai_cost(3600)
        assert cost == pytest.approx(0.23)

    def test_one_hour_without_speaker_labels(self) -> None:
        cost = calculate_assemblyai_cost(3600, speaker_labels=False)
        assert cost == pytest.approx(0.21)

    def test_subsecond_billing(self) -> None:
        # 0.5 seconds should still produce a non-zero cost
        cost = calculate_assemblyai_cost(0.5)
        assert cost == pytest.approx(0.5 * 0.23 / 3600)
        assert cost > 0

    def test_prices_come_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "assemblyai_cost_per_hour_usd", 0.15)
        monkeypatch.setattr(settings, "assemblyai_diarization_cost_per_hour_usd", 0.0)

        assert calculate_assemblyai_cost(3600) == pytest.approx(0.15)
