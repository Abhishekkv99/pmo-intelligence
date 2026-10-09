# -- Builder stage --
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv (pinned version; must read the uv.lock revision)
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application code and install project
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# -- Runtime stage --
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application code
COPY --from=builder --chown=appuser:appgroup /app/app /app/app
COPY --from=builder --chown=appuser:appgroup /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appgroup /app/alembic.ini /app/alembic.ini

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH"

# glibc gives every thread its own malloc arena and rarely returns a fragmented
# arena to the OS, so an asyncio service with a thread pool (the AssemblyAI SDK
# runs in one) keeps growing after each large transient allocation. Two arenas
# is the standard cap for long-running Python services.
ENV MALLOC_ARENA_MAX=2

# Install curl (health checks)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Local file storage (STORAGE_BACKEND=local, development and CI). A named
# volume mounted here takes this directory's owner when it is first created,
# so the non-root user can write uploads; without it the volume is root's.
RUN mkdir -p /app/uploads && chown appuser:appgroup /app/uploads

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
