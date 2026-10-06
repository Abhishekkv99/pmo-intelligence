import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.config import settings
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limiter import limiter
from app.utils.exceptions import AppError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Startup: ensure upload directory exists (local dev only). Guarded: the
    # non-root container on Fargate cannot create it, and S3 needs none.
    if settings.storage_backend == "local":
        os.makedirs(settings.local_upload_dir, exist_ok=True)

    # Startup: tracemalloc, only when memory diagnostics are switched on.
    from app.utils.memory import start_tracemalloc_if_enabled

    if start_tracemalloc_if_enabled():
        logging.getLogger(__name__).info("Memory diagnostics enabled (tracemalloc)")

    # Startup: give the configured emails the pmo_manager role. Non-fatal —
    # a DB hiccup at boot must never prevent the app from starting — and with
    # an empty list it opens no session at all.
    from app.services.bootstrap_admins import elevate_bootstrap_admins

    try:
        elevated = await elevate_bootstrap_admins()
        if elevated:
            logging.getLogger(__name__).info(
                "Elevated %d bootstrap admin(s) on startup", elevated
            )
    except Exception:
        logging.getLogger(__name__).warning(
            "Startup bootstrap admin elevation failed (non-fatal)", exc_info=True
        )

    # Startup: take over processing in the background. The queue's workers,
    # the takeover sweeps and the backlog re-queue all wait until this task
    # holds the processing lock - during a rolling deploy the old task keeps
    # processing for several minutes, and two owners would double-process
    # and sweep each other's live rows (see processing_ownership). Not
    # awaited here: uvicorn serves nothing until startup ends, and the
    # health check would kill a task that waited minutes to start. Requests
    # meanwhile enqueue into the not-yet-started queue as usual.
    from app.db.session import engine
    from app.services.processing_ownership import (
        ProcessingOwnership,
        hold_processing,
    )
    from app.services.processing_queue import get_processing_queue

    processing_queue = get_processing_queue()
    processing_ownership = ProcessingOwnership(engine)
    takeover = asyncio.create_task(
        hold_processing(processing_ownership, processing_queue),
        name="processing-takeover",
    )

    yield

    # Shutdown: stop the processing queue last, after every producer, then
    # give up ownership so the next task can take over. No drain: ECS allows
    # 30 s and a transcription takes minutes; the next owner's sweep makes
    # the interrupted rows retryable. A takeover still waiting is abandoned.
    takeover.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await takeover
    await processing_queue.stop()
    await processing_ownership.release()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PMO Intelligence",
        description="Live health monitoring for consultant placements",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Rate limiter state
    app.state.limiter = limiter

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
