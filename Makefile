# ========================
# PMO Intelligence - Top Level Makefile
# ========================

# Host ports for the local stack. Override them to run beside another project
# that holds 8000 or 3000, on every make command or in the environment:
#   make dev-build PMO_API_PORT=8100 PMO_WEB_PORT=3100
# The frontend image bakes in the API URL, so a new API port needs dev-build.
PMO_API_PORT ?= 8000
PMO_WEB_PORT ?= 3000
export PMO_API_PORT PMO_WEB_PORT

.PHONY: dev dev-build down down-clean test test-backend test-frontend test-e2e lint lint-backend lint-frontend format migrate migrate-new db-bootstrap clean help

# ========================
# Development
# ========================

dev: ## Start all services (backend, frontend, postgres)
	docker compose up

dev-build: ## Rebuild and start all services
	docker compose up --build

down: ## Stop all services
	docker compose down

down-clean: ## Stop all services and remove volumes
	docker compose down -v

# ========================
# Testing
# ========================

test: test-backend test-frontend ## Run all tests (backend unit + integration, frontend unit)

test-backend: ## Run backend tests (integration tests need Docker for testcontainers)
	cd backend && uv run pytest -v

test-frontend: ## Run frontend unit tests
	cd frontend && pnpm test

test-e2e: ## Run Playwright end-to-end tests against the stack on PMO_WEB_PORT/PMO_API_PORT
	cd frontend && E2E_BASE_URL=http://localhost:$(PMO_WEB_PORT) E2E_API_URL=http://localhost:$(PMO_API_PORT)/api/v1 pnpm test:e2e

# ========================
# Linting & Formatting
# ========================

lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint backend (ruff check, ruff format check, mypy strict)
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app

lint-frontend: ## Lint frontend (eslint, typecheck, prettier check)
	cd frontend && pnpm lint && pnpm typecheck && pnpm format:check

format: ## Auto-format all code
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && pnpm format

# ========================
# Database
# ========================

migrate: ## Run database migrations
	cd backend && uv run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new msg="description")
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

db-bootstrap: ## Bootstrap a deployed database as a one-off ECS task (usage: make db-bootstrap ENV=staging [ARGS=--rotate-password])
	@test -n "$(ENV)" || { echo "usage: make db-bootstrap ENV=staging [ARGS=--rotate-password]"; exit 2; }
	scripts/db-bootstrap.sh $(ENV) $(ARGS)

# ========================
# Utilities
# ========================

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true

help: ## Show this help message
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
