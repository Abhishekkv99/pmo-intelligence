# Architecture Overview

> **Status**: Sprint 1 in progress (Phase 1, 2026-10-08). **Built**: the backend skeleton (see "Backend (as built)"), with migrations 001–002 and sign-in for tenant members with a role, the frontend skeleton (see "Frontend (as built)"), local development with CI/CD (see "Local development and CI/CD (as built)"), and the staging infrastructure with PMO's Azure OpenAI and the Entra SSO app (see "Infrastructure (as built)"). Everything else is the planned design from `docs/PRD.md`; update each section as it is built.

## System Design
PMO Intelligence has 3 inputs, 1 queue, 2 pipelines and 1 health model. Every input becomes a signal, and every placement gets one health reading.

![PMO Intelligence architecture · 3 inputs, 1 queue, 2 pipelines, 1 health model](assets/architecture.png)

- **Session recordings** (S3 folder, upload, URL) and **Teams group chat** (Graph poll every 2 to 5 min) → **Processing queue** (one owning task, N workers, chat jobs first)
- Processing queue → **Session pipeline** (transcribe, roles, signals, actions) and **Chat pipeline** (classify, signals, cadence)
- Both pipelines → **Signal store** (signals with quotes) → recompute → **Health model** (6 scores, trend, RAG, risk flags)
- **Placement register** (admin pages, CSV import) → Health model (context: dates, extension, owners)
- Health model → polls 30 s → **Dashboard and alerts** (live board, email)

Recordings and chat both pass through the one processing queue into their pipelines. Everything they extract lands in the signal store. The health model recomputes the placement after every job and reads the register for context. The dashboard and alerts read the latest snapshot.

It uses the same stack as Interview Intelligence in a new repository, with three new pieces: a Microsoft Graph connector for Teams, the signal store with the health model, and a dashboard built around people rather than recordings.

**What is deliberately not shared**: no shared database, no shared service code at runtime, no monorepo. Files worth copying (the processing queue, the ownership lock, the LLM factory, the entitlement helper shape, the test conftests) are copied in and allowed to diverge.

## Backend (as built)
FastAPI app in `backend/app/`, layered routes → services → repositories → models.

| Area | Path | Notes |
|------|------|-------|
| App and lifespan | `app/main.py` | Startup: bootstrap-admin grant, then the processing takeover in a background task. Shutdown: queue stop, then lock release. |
| Settings | `app/config.py` | `pydantic-settings`, env vars or `.env` |
| Routes | `app/api/v1/{health,auth,processing}.py` | See `docs/API.md` |
| Entitlement | `app/utils/entitlements.py`, `app/dependencies.py` | Role model below; guards `require_roles`, `require_placement_scope`, `require_logged_placement_scope` |
| Enumerations | `app/models/enums.py` | `Role`, `GLOBAL_ROLES`, `ConsultantStatus`, `ExtensionStatus`, `PlacementStatus`, `JobStatus`; stored as strings with CHECK constraints |
| Models | `app/models/` | `user`, `refresh_token`, `register` (consultants, clients, projects, placements), `access_log`, `processing_job`, `processing_cost` |
| Processing queue | `app/services/processing_queue.py` | Priority queue, N workers; tiers `CHAT_PRIORITY` < `SESSION_PRIORITY` < `BACKLOG_PRIORITY`; dedup on `(kind, id)`; runners registered per kind (`register_runner`) |
| Ownership lock | `app/services/processing_ownership.py` | Postgres advisory lock on an AUTOCOMMIT connection, 30 s heartbeat; takeover steps registered (`register_takeover_sweep` before start, `register_takeover_requeue` after) |
| LLM factory | `app/ai/llm_factory.py` | Cached Azure OpenAI chat and embedding clients with a finite timeout (300 s) |
| Cost tracker | `app/services/cost_tracker.py` | Pure cost functions for LLM, embedding and transcription calls |
| Auth | `app/api/v1/auth.py`, `app/services/{auth,sso}_service.py` | Entra ID SSO (authorization code + PKCE, code exchanged by the backend; identity scopes only, no Microsoft token kept); members of the tenant with a role only (see the role model); local password auth only when `LOCAL_AUTH_ENABLED` (dev and CI), under the same role rule |
| Role grants | `app/services/user_roles.py`, `app/cli/user_role.py` | Grant, change or remove a role by email, or list users; run as a one-off ECS task with `make user-role` until the Admin "Users and roles" page exists |
| Migrations | `alembic/versions/001_create_initial_schema.py`, `002_drop_user_ms_tokens.py` | Async Alembic; 001 enables pgvector and builds the Sprint 0 schema; 002 drops the stored Microsoft tokens from `users` |
| Admin commands | ECS task definition `<env>-admin-cli` (`infra/modules/environment/admin_cli.tf`) | The backend image with `DATABASE_URL`, run by `scripts/user-role.sh` in the backend's subnets and security group |
| Database bootstrap | `app/cli/db_bootstrap.py` | One-off ECS task per deployed environment: creates the `pmo_app` login (random password), makes it owner of the database and `public` schema, creates `vector`, and writes `DATABASE_URL` into the app secret. Idempotent; `--rotate-password` rotates. Run with `make db-bootstrap ENV=<env>` |

**Role model**:
- `users.role` is nullable, one of `pmo_manager | sme | tech_lead | ps | admin`.
- `pmo_manager` and `admin` read every placement.
- `sme`, `tech_lead` and `ps` read the placements that name them (`placements.ps_user_id`, `placements.sme_user_id`, `projects.tech_lead_user_id`).
- **Signing in needs a role.** Only an active member of the InformationTech tenant whose user row holds a role may sign in, refresh a session or make any request (`may_use_app`).
  - Guests are refused by the id-token claim `acct` (0 member, 1 guest); a token without the claim is refused too.
  - SSO finds the user by Entra object id, then by email (a user granted a role ahead of their first sign-in is linked then). It creates a row only for a bootstrap admin, as `pmo_manager`. Anyone else without a row, or with no role, is refused with 403 and no row is written.
  - A removed role or a disabled account ends access: refresh revokes every refresh token of the user, and each request re-checks the role, so an open page stops within the 15-minute access-token life.
  - Every refusal logs a WARNING (sign-in, refresh, request).
- `NULL` reads nothing either, should a row without a role ever reach the scope check.
- Roles are granted with `make user-role ENV=<env> EMAIL=... ROLE=...` (`ROLE=none` removes one, `ARGS=--list` lists users).
- A denied by-id read answers 404, identical to a missing row, and logs a WARNING with user id and role.
- `BOOTSTRAP_ADMIN_EMAILS` raises listed users to `pmo_manager` at startup and at first sign-in (elevate-only).

## Frontend (as built)
Next.js 16.3.8 App Router app in `frontend/`, TypeScript strict, React 19.2, shadcn/ui, SWR, Tailwind 4. Packages via pnpm 12 (`packageManager: pnpm@12.6.0`; build-script approvals in `pnpm-workspace.yaml` `allowBuilds`). Node 22 or later.

| Area | Path | Notes |
|------|------|-------|
| Root layout | `src/app/layout.tsx` | Theme (light/dark/system), `AuthProvider`, `SWRProvider`, toasts; metadata from `APP_NAME` and `APP_TAGLINE` |
| Shell | `src/components/layout/{MainLayout,Sidebar,Header,ThemeToggle}.tsx` | Sidebar: Risk board, Actions, Admin (global roles only), Settings; header: app name, theme toggle, user menu with sign-out |
| Pages | `src/app/page.tsx` (Risk board), `actions/`, `admin/`, `settings/`, `login/`, `auth/callback/microsoft/` | Risk board, Actions and Settings are empty-state placeholders; Admin shows the processing queue |
| Admin | `src/components/admin/{AdminView,ProcessingStatusPanel}.tsx`, `src/hooks/useProcessingStatus.ts` | Queue depth, running jobs by kind, backend memory; polls every 5 s while busy, 30 s when idle; other roles see a no-access message and the queue is never requested |
| Roles | `src/lib/roles.ts` | Mirrors `Role` and `GLOBAL_ROLES` from `backend/app/models/enums.py`; `hasGlobalRole()` |
| Routes and API paths | `src/lib/constants.ts` | `ROUTES`, `API_ROUTES`, `APP_NAME`, `APP_TAGLINE` |
| API client | `src/lib/api.ts`, `src/lib/auth-token.ts` | Bearer token held in memory; one shared, time-limited refresh on a 401, one retry |
| Route guard | `src/proxy.ts` | No refresh cookie on a protected path → `/login`; a cookie on `/login` or the callback → `/` |
| Generic UI | `src/components/common/`, `src/components/ui/` | Empty state, error fallback, pagination, date-range filter, spinner; the shadcn component set |
| Health check | `src/app/api/health/route.ts` | `GET /api/health` for the load balancer |
| Tests | `src/**/*.test.ts(x)` (Vitest, Testing Library, jsdom), `tests/e2e/` (Playwright) | See `docs/tracking/TESTS.md` |

**Auth flow**:
1. The login page offers only "Sign in with Microsoft". `useSSOLogin` fetches `/auth/sso/microsoft/config`, creates a PKCE verifier (kept in `sessionStorage`) and sends the browser to the Entra authorize URL.
2. Entra redirects to `/auth/callback/microsoft`. The page posts the code, the verifier and the redirect URI to `/auth/sso/microsoft/callback`. The backend refuses a guest or a user without a role with 403, and the page shows the reason it returns. Otherwise it sets the `refresh_token` httpOnly cookie and returns an access token.
3. The page stores the access token in memory and does a full navigation to `/`, so the proxy sees the new cookie.
4. On every page load `AuthProvider` restores the session: `POST /auth/refresh` (cookie) for a new access token, then `GET /auth/me` for the user and role. It sends a signed-out user to `/login` and a signed-in user away from `/login` to `/`.
5. A request that answers 401 triggers one shared refresh and one retry. If that fails, the session expires and the browser goes to `/login`.

**Role in the UI**: the frontend only decides what to show; the backend enforces every permission. The Admin link appears for `pmo_manager` and `admin` only. A user with no role cannot sign in; the callback page shows the backend's message.

**Tooling**: `pnpm lint` (ESLint with Next's rules and `eslint-config-prettier`), `pnpm typecheck` (`tsc --noEmit`), `pnpm format` / `format:check` (Prettier 3 defaults over every file), `pnpm test` (Vitest), `pnpm test:e2e` (Playwright; signs in with local auth, so it needs a backend with `LOCAL_AUTH_ENABLED=true`).

## Local development and CI/CD (as built)
**Local stack** (`docker-compose.yml`):

| Service | Image | Host port | Notes |
|---------|-------|-----------|-------|
| postgres | `pgvector/pgvector:pg16` | 5432 | Database `pmo_intelligence`, user and password `postgres`; data in the `postgres_data` volume |
| backend | `backend/Dockerfile` | `PMO_API_PORT`, default 8000 | `LOCAL_AUTH_ENABLED=true`, local file storage in the `upload_data` volume; healthy when `/api/v1/health` answers |
| frontend | `frontend/Dockerfile` | `PMO_WEB_PORT`, default 3000 | Built with `NEXT_PUBLIC_API_URL=http://localhost:<PMO_API_PORT>/api/v1`; healthy when `/api/health` answers |

- The API and web host ports are configurable so the stack can run beside another project. The Makefile sets `PMO_API_PORT` and `PMO_WEB_PORT` (defaults 8000 and 3000) and exports them to compose. The backend's `FRONTEND_URL` and `AZURE_REDIRECT_URI`, the frontend's API URL, and Playwright's `E2E_BASE_URL`/`E2E_API_URL` (via `make test-e2e`) follow them. Inside the containers the servers always listen on 8000 and 3000, and CI uses the defaults.
- The images do not run migrations. `make migrate` runs `alembic upgrade head` from the host against port 5432.
- Commands run outside Docker (`uv run ...`, `make migrate`, `make test-backend`) read `backend/.env`. `.env.example` at the repository root lists every setting `app/config.py` reads.
- The Makefile is POSIX and runs from Git Bash on Windows (GNU make from `winget install ezwinports.make`) and on the Ubuntu CI runners. `make help` lists the targets.

**Images**:
- **Backend**: two stages on `python:3.12-slim`. uv `0.9.18` (pinned to read the revision-3 `uv.lock`) installs the locked dependencies without dev extras. The runtime stage runs as a non-root user with `MALLOC_ARENA_MAX=2`, and curl for the health check.
- **Frontend**: three stages on `node:22-alpine`. pnpm `12.6.0` comes through corepack, and `pnpm-workspace.yaml` is copied for the build-script approvals. The Next.js `standalone` output runs as a non-root user with `HOSTNAME=0.0.0.0`, because the server binds to `$HOSTNAME` and Docker sets that to the container id.
- Each build context has a `.dockerignore`. Virtual environments, `node_modules`, build output, caches, `.env` files and tests stay out of the images.

**CI** (`.github/workflows/ci.yml`, on push and pull request to `main` and `develop`):

| Job | Runs when | Steps |
|-----|-----------|-------|
| Detect Changes | always | Path filters: backend, frontend, compose file; a change to `ci.yml` runs everything. A pull request compares with its base branch, a push to `main` with the previous commit, and a push to any other branch with `main`, so on `develop` everything not yet released counts as changed |
| Backend CI | `backend/**` changed | `uv sync --frozen`; ruff check; ruff format check; `mypy app` (strict); unit tests; integration tests (testcontainers starts pgvector) |
| Frontend CI | `frontend/**` changed | `pnpm install --frozen-lockfile`; eslint; `tsc --noEmit`; Prettier check; Vitest; `next build` |
| E2E Tests | backend, frontend or compose file changed | `docker compose up --build --wait`; `alembic upgrade head` from the runner; Playwright (Chromium) with local auth; stack logs on failure; report uploaded |
| Deploy to staging | push to `develop`, every job above passed or skipped, `vars.AWS_ROLE_ARN` set | See below |

- Checkout uses the default `GITHUB_TOKEN`, so there is no personal token to renew.
- The tools are pinned: uv `0.9.18`, pnpm from the `packageManager` field, Node 22. The actions are on their node24 majors.
- `make lint` runs the same lint gates as CI.

**Deploy** (the `deploy-staging` job in `ci.yml`):
- Only the side that changed since the previous commit on `develop` is rebuilt and redeployed. Redeploying the backend restarts processing, so a frontend-only push leaves it alone.
- AWS access is through OIDC, assuming `vars.AWS_ROLE_ARN`. Only this job has `id-token: write`.
- Images go to ECR `pmo-intelligence-backend` and `pmo-intelligence-frontend` with the tags `sha-<commit>` and `staging-latest`. Then `aws ecs update-service --force-new-deployment` runs.
- The identifiers are repository variables, because none are secret with OIDC: `AWS_ROLE_ARN`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER_NAME`, `ECS_STAGING_BACKEND_SERVICE`, `ECS_STAGING_FRONTEND_SERVICE`. Their values come from the Terraform outputs (Sprint 0 Phase 4). Until `AWS_ROLE_ARN` is set, the job is skipped.
- `main` does not deploy yet. The production path is added when the production infrastructure is applied.

## Infrastructure (as built)
AWS account **ITC Sandbox PD Intelligence (`260172548683`)**, eu-west-2. Nothing on AWS is shared with Interview Intelligence. Terraform state lives in `pmo-intelligence-tfstate-260172548683`, with one key per stack and native S3 locking. Steps and commands are in `docs/DEPLOYMENT.md`.

| Stack | Path | Owns |
|-------|------|------|
| Bootstrap | `infra/bootstrap/` | The state bucket: versioned, SSE-S3, public access blocked, TLS-only |
| Shared | `infra/shared/` | VPC `10.40.0.0/16`: 2 public subnets (ALB, tasks) and 2 private (RDS, no internet route); S3 gateway endpoint; ECR `pmo-intelligence-backend`/`-frontend`; ECS cluster `pmo-intelligence`; GitHub OIDC provider and the `pmo-intelligence-github-deploy` role (`develop` runs only); the deny-deletion policy |
| Staging | `infra/environments/staging/` → `infra/modules/environment/` | Hosted zone `pmo-intelligence-staging.itcapp.ai` (delegated by one NS record in `itcapp.ai`, account `430006376054`); ACM certificate; ALB (HTTPS, `/api/*` to the backend, HTTP redirected); RDS `pmo-intelligence-staging` (PostgreSQL 16, `db.t4g.micro`, private, master password managed by RDS); secret `pmo-intelligence/staging/app`; media bucket; SES identity; log groups; per-environment IAM roles; ECS services `pmo-intelligence-staging-backend`/`-frontend` |

- **Traffic**: internet → ALB security group (80, 443) → backend (8000) and frontend (3000) security groups. Only the backend reaches RDS (5432).
- **Egress**: tasks run in public subnets with a public IPv4 each (no NAT) to reach Azure OpenAI, AssemblyAI, Entra, ECR and CloudWatch. S3 traffic goes through the gateway endpoint.
- **Database isolation**: staging has its own instance. Production gets another at product Phase 5. The app will connect as `pmo_app`, not the master user (database bootstrap, Phase 4).
- **Protection**: `prevent_destroy` on the RDS instance (which also has deletion protection and a final snapshot), the media bucket, the app secret, the hosted zone and the state bucket. Everything else can be recreated.
- **Entra SSO app** (`scripts/entra/Register-SsoApp.ps1`): one single-tenant app registration, "PMO Intelligence", for every environment, with Web redirect URIs and the optional id-token claim `acct`. Assignment is not required in Entra; the backend admits only members of the tenant with a role. Each environment has its own client secret, written into its app secret.
- **Azure OpenAI** (`infra/azure/`): PMO's own resource group `rg-pmo-intelligence-swc` and resource `oai-pmo-intelligence-swc` in Sweden Central, with Data Zone Standard deployments per environment (`gpt-5.4-mini-<env>`, `text-embedding-3-small-<env>`). Prompt processing stays in the EU data zone, and cost is tracked per resource group. AssemblyAI uses a PMO-only API key.
- **Credential expiry reminders** (`infra/shared/`): EventBridge Scheduler emails the SNS topic `pmo-intelligence-credential-expiry` 30, 14 and 3 days before each date in `credential_expiries`. It tracks the Teams Graph certificate and the Entra SSO client secret for staging.

## Component Architecture
| Component | Technology | Responsibility | Reuse or new |
|-----------|-----------|----------------|--------------|
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 async, Alembic, Pydantic | Routes → services → repositories → models; scope check on every by-id route | Reuse the layering and the repo skeleton |
| Database | PostgreSQL 16 + pgvector | Register, sessions, messages, signals (with embeddings), snapshots, flags, access log | Reuse; embeddings let a reviewer search "who else had this blocker" |
| Transcription | AssemblyAI with speaker diarization; Teams' own transcript when a recording comes through Graph | Diarized utterances for the session pipeline | Reuse the shared AssemblyAI client |
| LLM | Azure OpenAI gpt-5.4-mini through the LLM factory, LangGraph graphs, structured output | Session and chat pipelines; every node non-fatal, timed, costed, with a timeout | Reuse the factory, the cost tracker, the timeout setting, the non-fatal node pattern |
| Processing | One process-wide priority queue with N workers, a Postgres advisory lock so one task owns processing during a deploy, startup sweeps, a per-job session | Runs pipeline jobs; chat jobs ahead of session jobs | Reuse as is; it cost three hotfixes to get right |
| Teams connector | Microsoft Graph: channel or chat messages, later meeting recordings and transcripts | Polls watched groups every 2–5 min with delta tokens (channels) or a last-modified watermark (chats) | New |
| Signals and health | signals, health_snapshots, risk_flags, actions tables; a pure scoring module with weights and thresholds in configuration | Six dimension scores, overall, trend, RAG, triggers → snapshot | New |
| Alerts | Amazon SES email now; a Teams message to a PMO channel once the connector can write | Immediate, daily digest, weekly summary | Reuse the SES sender from the daily report |
| Frontend | Next.js 16 App Router, TypeScript strict, shadcn/ui, SWR, TanStack Table, Recharts, dark mode | Risk board, consultant page, session page, actions, admin | Reuse the component library, the auth client, the admin page patterns |
| Auth | Microsoft Entra ID SSO only, roles on the user row, bootstrap admin list from configuration | Role plus placement scope; 404 outside scope; access log | Reuse; replace the UK/US entitlement with role plus consultant scope |
| Infra | AWS eu-west-2: ECS Fargate, RDS, S3, ALB, Secrets Manager, CloudWatch, Terraform | Staging and production environments | Reuse the modules; fully separate from Interview Intelligence (decided 2026-10-07) in its own AWS account (ITC Sandbox PD Intelligence, `260172548683`): its own VPC, VPC endpoints, RDS instance, ALBs, bucket, GitHub OIDC provider and Terraform state. The only link outside the account is one NS record in the `itcapp.ai` zone delegating `pmo-intelligence-staging.itcapp.ai` to PMO's hosted zone. Replaces the starter's "a separate RDS database on the existing instance, its own bucket, its own ALB rules or hostname" |
| CI | GitHub Actions: unit, integration (testcontainers), Playwright; build-and-push with path filters | Gate every merge | Reuse |

## Teams Connector
- **Permission routes, in order of preference**: (1) resource-specific consent (RSC) per group with `ChannelMessage.Read.Group` / `ChatMessage.Read.Chat`; (2) application permissions `ChannelMessage.Read.All` / `Chat.Read.All`, which are Microsoft protected APIs that need approval; (3) delegated permissions through a service account, which is fragile. The full comparison is in the PRD.
- **Sync**: poll every 2–5 min; store the delta token or watermark on `teams_groups`. Change notifications are a later optimisation, because chat subscriptions expire within the hour.
- **Meeting recordings (later)**: `OnlineMeetingRecording.Read.All`, `OnlineMeetingTranscript.Read.All` plus an application access policy assigned to the organisers.
- **Risks**: protected-API lead time; tenant admin consent; Graph throttling on the first history pull; edited or deleted messages (store lastModified, honour deletion); partner tenants needing separate consent.

## Data Model
The placement is the unit of health; the consultant, the client and the project are its context. Every table carries `id`, `created_at`, `updated_at`.

| Table | Key Fields | Notes |
|-------|-----------|-------|
| consultants | full_name, email, entra_oid (nullable), phone, skills, status (bench / placed / left) | One row per person; entra_oid links the Teams author to the consultant |
| clients | name, normalized_name, industry | Dedup on normalized_name |
| projects | client_id, name, client_manager_name, tech_lead_user_id, start_date | One client can run several projects |
| placements | consultant_id, project_id, start_date, expected_end_date, extension_status (not_due / due / requested / confirmed / declined), rate_band, ps_user_id, sme_user_id, status (active / ended / terminated), ended_reason | The unit everything else hangs off; ended_reason is what a forecast model would later learn from |
| teams_groups | placement_id (nullable), project_id (nullable), graph_team_id, graph_channel_id or graph_chat_id, kind (channel / group_chat), is_active, last_synced_at, delta_token | One Teams conversation watched for one placement or project |
| sessions | placement_id, kind (onboarding / technical / check_in / escalation / other), held_at, duration_seconds, source (s3 / upload / url / graph), recording_key, graph_meeting_id, status (uploaded → transcribing → transcribed → analyzing → completed / failed), error_message | One recorded PMO call |
| session_transcripts | session_id (unique), full_text, utterances (JSONB), speaker_roles (JSONB), summary, session_class | Diarized transcript and the attributed roles |
| messages | teams_group_id, graph_message_id (unique with group), author_entra_oid, author_role (consultant / pmo_manager / sme / tech_lead / ps / other), posted_at, body_text, reply_to_message_id, message_class, is_noise | The raw chat, kept so a flag can quote it |
| signals | placement_id, source_kind (session / message), source_id, dimension, polarity, severity (1–3), confidence (0–1), quote, note, occurred_at, embedding (1536D) | The one table the health model reads; indexed on (placement_id, occurred_at) |
| issues | placement_id, topic, first_seen_at, last_seen_at, occurrence_count, status (open / resolved), resolved_at | A blocker followed across sessions; the repeated-blocker trigger reads it |
| actions | placement_id, source_kind, source_id, owner_role, owner_user_id (nullable), description, due_text, due_date (nullable), status (open / done / overdue), closed_at | What was agreed on a call or in the group |
| health_snapshots | placement_id, computed_at, delivery, technical, relationship, engagement, onboarding, communication, overall, trend, risk_level, signal_count, weights_version | One row per recompute; the dashboard reads the latest, the chart reads the history |
| risk_flags | placement_id, trigger, severity, opened_at, evidence_signal_ids, closed_at, closed_by_user_id, closing_note | Open until a person closes it |
| users | email, full_name, entra_oid, role (pmo_manager / sme / tech_lead / ps / admin), is_active | Role is the entitlement; scope is derived from the placements naming the user |
| processing_jobs, processing_costs, refresh_tokens | as in Interview Intelligence | Costs keyed by session_id or message_id, nullable, so chat runs are costed too |
| access_log | user_id, placement_id, route, at | Who looked at whom |

**Open before the first migration**: does a Teams group map to a placement or a project (a project group with two consultants needs the author's identity to attribute a message), and is the register owned here or imported from the PS team's system of record? These are BACKLOG questions 1 and 3.

**Built in migration 001 (Sprint 0)**: `users`, `refresh_tokens`, `consultants`, `clients`, `projects`, `placements`, `processing_jobs`, `processing_costs`, `access_log`, plus the `vector` extension. Differences from the draft above:
- `users`: no `branch`/`access_level` (UK only); `role` is nullable. Migration 002 (Sprint 1) drops `ms_access_token`, `ms_refresh_token` and `ms_token_expires_at`: sign-in keeps no Microsoft token, because Teams is read with the Graph app's own credential.
- `processing_jobs` is generic: `kind`, `subject_id` (no foreign key; the subject's table depends on `kind`), `status`, `stage`, `started_at`, `completed_at`, `error_message`, `retry_count`.
- `processing_costs.session_id` and `message_id` have no foreign keys yet; they are added when `sessions` and `messages` arrive.
- `access_log` carries `created_at`/`updated_at` as well as `at`; its index is on (`placement_id`, `at`).
- `consultants.status` defaults to `placed`; `placements.extension_status` defaults to `not_due` and `status` to `active`.
- Every enumerated column has a CHECK constraint built from `app/models/enums.py`.
