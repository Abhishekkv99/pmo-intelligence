"""Cost tracking for AI pipeline operations.

Centralizes pricing constants and cost calculation functions for
AssemblyAI transcription, Azure OpenAI gpt-5.4-mini LLM calls, and Azure OpenAI
text-embedding-3-small embedding generation.
"""

# Pricing constants (as of June 2026)
# gpt-5.4-mini (Azure OpenAI standard PAYG)
GPT54_MINI_INPUT_COST_PER_TOKEN = 0.75 / 1_000_000  # $0.75 per 1M input tokens
GPT54_MINI_OUTPUT_COST_PER_TOKEN = 4.50 / 1_000_000  # $4.50 per 1M output tokens

# text-embedding-3-small
EMBEDDING_COST_PER_TOKEN = 0.02 / 1_000_000  # $0.02 per 1M tokens

# AssemblyAI
ASSEMBLYAI_COST_PER_SECOND = 0.15 / 3600  # $0.15 per hour, pro-rated to the second


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


def calculate_assemblyai_cost(audio_duration_seconds: float) -> float:
    """Calculate cost for AssemblyAI transcription.

    Billed pro-rated to the second at $0.15/hour.
    Returns cost in USD.
    """
    return audio_duration_seconds * ASSEMBLYAI_COST_PER_SECOND
