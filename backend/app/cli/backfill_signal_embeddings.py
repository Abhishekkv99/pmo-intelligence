"""Embed the signals that have no embedding yet.

The session job embeds a session's signals after its analysis; when that step
fails (Azure unavailable, a timeout) they stay without one, and nothing
retries them. This fills them session by session, oldest call first, as the
job would: in requests of ``SIGNAL_EMBEDDING_BATCH_SIZE``, one commit and a
cost row per request. A session that fails is logged and skipped, and the
exit code is 1 when any did.

Runs locally, or on a deployed environment as a one-off task from the
backend's task definition, which has the Azure OpenAI settings:
``make backfill-embeddings ENV=staging``; see docs/DEPLOYMENT.md.

Usage:
    python -m app.cli.backfill_signal_embeddings            # embed them
    python -m app.cli.backfill_signal_embeddings --dry-run  # count only
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.signal_repo import SignalRepository
from app.db.session import async_session_factory
from app.models.enums import SourceKind
from app.services.signal_embeddings import SignalEmbeddingService

logger = logging.getLogger("backfill_signal_embeddings")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def backfill(
    *, dry_run: bool, session_factory: SessionFactory = async_session_factory
) -> int:
    kind = SourceKind.SESSION.value
    async with session_factory() as db:
        repo = SignalRepository(db)
        missing = await repo.count_without_embedding(kind)
        sessions = await repo.sources_without_embedding(kind)
    logger.info(
        "%d signal(s) in %d session(s) have no embedding", missing, len(sessions)
    )
    if dry_run or not sessions:
        return 0

    embedded = 0
    failed = 0
    for session_id in sessions:
        async with session_factory() as db:
            try:
                embedded += await SignalEmbeddingService(db).embed_session(session_id)
            except Exception:
                await db.rollback()
                failed += 1
                logger.exception("Session %s: embedding failed", session_id)
    logger.info(
        "Embedded %d signal(s) in %d session(s); %d session(s) failed",
        embedded,
        len(sessions) - failed,
        failed,
    )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only count the signals without an embedding",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    return asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
