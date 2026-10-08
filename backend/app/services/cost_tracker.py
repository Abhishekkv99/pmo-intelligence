"""Cost tracking for AI pipeline operations.

Centralizes pricing constants and cost calculation functions for
AssemblyAI transcription, Azure OpenAI gpt-5.4-mini LLM calls, and Azure OpenAI
text-embedding-3-small embedding generation. AssemblyAI's prices are settings,
because the model in use is.
"""

from app.config import settings

# Pricing constants (as of June 2026)
# gpt-5.4-mini (Azure OpenAI standard PAYG)
GPT54_MINI_INPUT_COST_PER_TOKEN = 0.75 / 1_000_000  # $0.75 per 1M input tokens
GPT54_MINI_OUTPUT_COST_PER_TOKEN = 4.50 / 1_000_000  # $4.50 per 1M output tokens

# text-embedding-3-small
EMBEDDING_COST_PER_TOKEN = 0.02 / 1_000_000  # $0.02 per 1M tokens


def calculate_llm_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a gpt-5.4-mini API call (Azure OpenAI).

    Returns cost in USD.
    """
    return (
        input_tokens * GPT54_MINI_INPUT_COST_PER_TOKEN
        + output_tokens * GPT54_MINI_OUTPUT_COST_PER_TOKEN
    )


def calculate_embedding_cost(total_tokens: int) -> float:
    """Calculate cost for text-embedding-3-small.

    Returns cost in USD.
    """
    return total_tokens * EMBEDDING_COST_PER_TOKEN


def calculate_assemblyai_cost(
    audio_duration_seconds: float, *, speaker_labels: bool = True
) -> float:
    """Calculate cost for AssemblyAI transcription.

    The model's hourly rate, plus diarization when speakers are labelled,
    pro-rated to the second. Returns cost in USD.
    """
    per_hour = settings.assemblyai_cost_per_hour_usd
    if speaker_labels:
        per_hour += settings.assemblyai_diarization_cost_per_hour_usd
    return audio_duration_seconds * per_hour / 3600
