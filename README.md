# PMO Intelligence

Live health for every consultant placement. PMO Intelligence reads recorded PMO sessions and the Teams group conversation for each placement and extracts signals, each backed by a quote. A deterministic health model turns the signals into a score per dimension, a trend, a RAG level and risk flags with their evidence. The PMO, tech leads and placement specialists act on the flags; the tool never acts on a consultant by itself.

> Status: Sprint 0 (bootstrap). Sign-in, roles, the empty dashboard, local development and CI are built; the product features follow from Sprint 1. See `docs/planning/ROADMAP.md`.

## Stack
- **Backend**: FastAPI, Python 3.12, SQLAlchemy 2.0 async, Alembic, Pydantic; PostgreSQL 16 with pgvector
- **Frontend**: Next.js 16 App Router, TypeScript strict, shadcn/ui, SWR, Tailwind 4
- **Sign-in**: Microsoft Entra ID (local password sign-in only in development and CI)
- **Infrastructure**: AWS eu-west-2 (ECS Fargate, RDS, S3, ALB), Terraform, GitHub Actions

## Prerequisites
| Tool | Version | Notes |
|------|---------|-------|
| Docker with Compose | Docker Desktop on Windows or macOS | Runs the local stack and the integration tests (testcontainers) |
| uv | 0.9.18 | Python dependencies (`backend/uv.lock`) |
| Node.js | 22 or later | |
| pnpm | 12.6.0 | `corepack enable` picks it up from `frontend/package.json` |
| GNU make | 4.x | Windows: `winget install ezwinports.make`, then run `make` from Git Bash |

## Quick start
```bash
# 1. Settings for commands run outside Docker (migrations, backend tests)
cp .env.example backend/.env

# 2. Install dependencies
cd backend && uv sync && cd ..
cd frontend && pnpm install && cd ..

# 3. Build and start postgres, backend and frontend
make dev-build          # or: docker compose up -d --build

# 4. Create the schema (the images do not run migrations)
make migrate
```

Then open http://localhost:3000. The API is at http://localhost:8000/api/v1 (`/health` answers without sign-in).

**Ports in use?** If another project holds 8000 or 3000, pick other host ports with `PMO_API_PORT` and `PMO_WEB_PORT`. Pass the same values to every make command, or export them in your shell:

```bash
make dev-build PMO_API_PORT=8100 PMO_WEB_PORT=3100   # rebuild: the frontend bakes in the API URL
make test-e2e  PMO_API_PORT=8100 PMO_WEB_PORT=3100
```

The database stays on 5432. SSO sign-in on another web port also needs that port's callback URL registered in Entra.

The login page offers only Microsoft sign-in, which needs the `AZURE_*` settings. Without them, sign in through the API with local auth, as the end-to-end tests do: `POST /api/v1/auth/register`, then `POST /api/v1/auth/login`. A new account has no role; an email listed in `BOOTSTRAP_ADMIN_EMAILS` becomes a PMO manager.

The compose backend reads only the environment set on its service in `docker-compose.yml`, not `backend/.env`. To try SSO or a bootstrap admin in the stack, add those variables to that service locally and do not commit them.

## Common commands
| Command | What it does |
|---------|--------------|
| `make help` | List every target |
| `make dev` / `make dev-build` | Start the stack / rebuild and start it |
| `make down` / `make down-clean` | Stop the stack / stop it and delete its volumes |
| `make migrate` | Apply migrations (`alembic upgrade head`) |
| `make migrate-new msg="..."` | Generate a migration from the models |
| `make test` | Backend unit and integration tests, frontend unit tests |
| `make test-e2e` | Playwright end-to-end tests against the running stack (on `PMO_WEB_PORT`/`PMO_API_PORT`) |
| `make lint` | ruff, ruff format check, mypy strict; eslint, typecheck, Prettier check |
| `make format` | Format the backend (ruff) and the frontend (Prettier) |
| `make db-bootstrap ENV=staging` | One-off database bootstrap in a deployed environment (see `docs/DEPLOYMENT.md`) |
| `make user-role ENV=staging EMAIL=... ROLE=...` | Grant a role (`ROLE=none` removes it; `ARGS=--list` lists users) in a deployed environment (see `docs/DEPLOYMENT.md`) |

## CI and deployment
Every push and pull request to `main` or `develop` runs `.github/workflows/ci.yml`:
- lint, type checks, unit and integration tests for the parts that changed
- end-to-end tests against the compose stack

A push to `develop` that passes deploys the changed side to staging. Details are in `docs/ARCHITECTURE.md`, "Local development and CI/CD".

## Documentation
| Document | Contents |
|----------|----------|
| `docs/PRD.md` | Product requirements |
| `docs/ARCHITECTURE.md` | System design, what is built, data model |
| `docs/API.md` | Endpoints and access rules |
| `docs/planning/` | Current sprint, roadmap, backlog |
| `docs/tracking/` | Tests, features, changelog |
| `docs/integrations/TEAMS-GRAPH-SETUP.md` | Microsoft Teams (Graph) access setup |
