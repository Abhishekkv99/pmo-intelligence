"""Signal embeddings: each signal's quote and note as a 1536-number vector.

They let a reviewer later search "who else had this blocker" (no search page
yet; the HNSW index is in migration 006). The session job embeds a session's
signals after its analysis is stored, for a ``completed`` session only, through
``embed_session_signals``, which never fails the session: an error is logged
and the embeddings stay empty until the backfill command
(``app.cli.backfill_signal_embeddings``) fills them.

A session's signals are embedded in requests of at most
``SIGNAL_EMBEDDING_BATCH_SIZE``, all within ``SIGNAL_EMBEDDING_TIMEOUT_SECONDS``,
and written in one commit with a ``processing_costs`` row per request, costed
from the tokens Azure reports.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Sequence

from openai import AsyncAzureOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_factory import EMBEDDING_DIMENSIONS, build_embedding_client
from app.config import settings
from app.db.repositories.signal_repo import SignalRepository
from app.models.enums import SourceKind
from app.models.processing_cost import ProcessingCost
from app.models.signal import Signal
from app.services.cost_tracker import calculate_embedding_cost

logger = logging.getLogger(__name__)

EMBEDDING_OPERATION = "signal_embeddings"


class EmbeddingError(Exception):
    """Azure answered with something other than one vector per signal."""


def embedding_text(signal: Signal) -> str:
    """What is embedded: the quote, then the note on its own line."""
    if signal.note:
        return f"{signal.quote}\n{signal.note}"
    return signal.quote


class SignalEmbeddingService:
    def __init__(
        self, db: AsyncSession, *, client: AsyncAzureOpenAI | None = None
    ) -> None:
        self.db = db
        self.signals = SignalRepository(db)
        self._client = client

    async def embed_session(
        self, session_id: uuid.UUID, job_id: uuid.UUID | None = None
    ) -> int:
        """Embed the session's signals that have none; commit; return how many."""
        signals = await self.signals.without_embedding(
            SourceKind.SESSION.value, session_id
        )
        if not signals:
            return 0
        size = max(1, settings.signal_embedding_batch_size)
        async with asyncio.timeout(settings.signal_embedding_timeout_seconds):
            for start in range(0, len(signals), size):
                await self._embed(signals[start : start + size], session_id, job_id)
        await self.db.commit()
        return len(signals)

    async def _embed(
        self,
        batch: Sequence[Signal],
        session_id: uuid.UUID,
        job_id: uuid.UUID | None,
    ) -> None:
        client = self._client or build_embedding_client()
        started = time.perf_counter()
        response = await client.embeddings.create(
            model=settings.azure_embedding_deployment,
            input=[embedding_text(signal) for signal in batch],
        )
        elapsed = time.perf_counter() - started

        vectors = sorted(response.data, key=lambda item: item.index)
        if len(vectors) != len(batch):
            raise EmbeddingError(
                f"Asked for {len(batch)} embeddings, got {len(vectors)}"
            )
        for signal, item in zip(batch, vectors, strict=True):
            if len(item.embedding) != EMBEDDING_DIMENSIONS:
                raise EmbeddingError(
                    f"An embedding has {len(item.embedding)} dimensions, "
                    f"not {EMBEDDING_DIMENSIONS}"
                )
            signal.embedding = list(item.embedding)

        tokens = response.usage.total_tokens
        self.db.add(
            ProcessingCost(
                session_id=session_id,
                processing_job_id=job_id,
                service="azure_openai",
                operation=EMBEDDING_OPERATION,
                amount_usd=calculate_embedding_cost(tokens),
                input_tokens=tokens,
                model=settings.azure_embedding_deployment,
                duration_seconds=elapsed,
            )
        )


async def embed_session_signals(
    db: AsyncSession, session_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> None:
    """Embed a completed session's signals; a failure is logged, never raised."""
    try:
        count = await SignalEmbeddingService(db).embed_session(session_id, job_id)
    except Exception:
        await db.rollback()
        logger.exception(
            "Embedding the signals of session %s failed; they stay empty until "
            "the backfill command is run",
            session_id,
        )
        return
    if count:
        logger.info("Session %s: %d signal(s) embedded", session_id, count)
