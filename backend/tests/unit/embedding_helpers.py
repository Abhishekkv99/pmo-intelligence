"""A fake Azure OpenAI embedding client shared by the embedding tests."""

import asyncio
from types import SimpleNamespace
from typing import Any

from app.ai.llm_factory import EMBEDDING_DIMENSIONS

TOKENS_PER_INPUT = 12


def vector(n: int, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """A distinct unit vector for the n-th input."""
    values = [0.0] * dimensions
    values[n % dimensions] = 1.0
    return values


class FakeEmbeddings:
    """Answers each request with one vector per input, in reverse order (Azure
    gives each its ``index``); records every request. The options (an error,
    a vector missing, other dimensions, a hang) apply to the requests numbered
    in ``bad_requests`` (from 1), or to every request when it is ``None``."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        missing: int = 0,
        dimensions: int = EMBEDDING_DIMENSIONS,
        hang: bool = False,
        bad_requests: set[int] | None = None,
    ) -> None:
        self.error = error
        self.missing = missing
        self.dimensions = dimensions
        self.hang = hang
        self.bad_requests = bad_requests
        self.requests: list[dict[str, Any]] = []
        self._served = 0

    async def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        self.requests.append({"model": model, "input": list(input)})
        number = len(self.requests)
        good = self.bad_requests is not None and number not in self.bad_requests
        if self.hang and not good:
            await asyncio.Event().wait()
        if self.error is not None and not good:
            raise self.error
        missing = 0 if good else self.missing
        dimensions = EMBEDDING_DIMENSIONS if good else self.dimensions
        data = [
            SimpleNamespace(index=i, embedding=vector(self._served + i, dimensions))
            for i in range(len(input) - missing)
        ]
        self._served += len(input)
        return SimpleNamespace(
            data=list(reversed(data)),
            usage=SimpleNamespace(
                prompt_tokens=TOKENS_PER_INPUT * len(input),
                total_tokens=TOKENS_PER_INPUT * len(input),
            ),
        )


class FakeEmbeddingClient:
    def __init__(self, **options: Any) -> None:
        self.embeddings = FakeEmbeddings(**options)
