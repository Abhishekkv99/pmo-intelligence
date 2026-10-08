# Architecture Overview

> **Status**: Sprint 1 in progress (Phase 3, 2026-10-09). **Built**: the backend skeleton (see "Backend (as built)"), with migrations 001–004 (003: the session and recordings tables; 004: recording scans), the ingestion building blocks (media storage, recording checks, upload, URL download with an SSRF guard, AssemblyAI client; no route uses them yet) the recordings folder scanner (on in staging since 2026-10-09, reading the main account's bucket through its bucket policy) the session service with its `session` job (copy or download, transcribe), and the recordings and session routes (no frontend yet), sign-in for tenant members with a role, and the placement register with CSV import (also in "Backend (as built)"), the frontend skeleton with the Admin register and import (see "Frontend (as built)"), local development with CI/CD (see "Local development and CI/CD (as built)"), and the staging infrastructure with PMO's Azure OpenAI and the Entra SSO app (see "Infrastructure (as built)"). Everything else is the planned design from `docs/PRD.md`; update each section as it is built.

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
| Settings | `app/config.py` | `pydantic-settings`, env vars or `.env`; transcription on AssemblyAI's EU endpoint (`ASSEMBLYAI_BASE_URL`) with `ASSEMBLYAI_SPEECH_MODELS` `["universal-3-5-pro", "universal-2"]`; `APP_DEBUG` (SQL echo) is off unless set, and compose and `.env.example` turn it on for development |
| Routes | `app/api/v1/{health,auth,processing,register,users,recordings,sessions}.py` | See `docs/API.md` |
| Upload body limit | `app/middleware/body_limit.py` | `POST /api/v1/sessions/upload` only: answers 413 once the body passes `MAX_UPLOAD_SIZE_MB` + 1 MiB, at once from `Content-Length` or as chunks arrive, so an oversized upload is never spooled to disk in full (Starlette parses a multipart body before the route runs) |
| Placement register | `app/services/register_service.py`, `app/services/register_import.py`, `app/db/repositories/{consultant,client,project,placement}_repo.py` | Create and edit consultants, clients, projects and placements; CSV import. Rules below |
| Request session | `app/dependencies.py` (`DbSession`) | One session per request, committed **before** the response is sent (`Depends(get_db, scope="function")`), so a client never sees a success for an uncommitted write; every route and guard takes it through this alias, and a unit test checks every route |
| Entitlement | `app/utils/entitlements.py`, `app/dependencies.py` | Role model below; guards `require_roles`, `require_placement_scope`, `require_logged_placement_scope` |
| Enumerations | `app/models/enums.py` | `Role`, `GLOBAL_ROLES`, `ConsultantStatus`, `ExtensionStatus`, `PlacementStatus`, `JobStatus`, `SessionKind`, `SessionSource`, `SessionStatus`, `FolderMatchStatus`, `ScanStatus`; stored as strings with CHECK constraints |
| Models | `app/models/` | `user`, `refresh_token`, `register` (consultants, clients, projects, placements), `session` (recording folders, source recordings, recording scans, sessions, session transcripts), `access_log`, `processing_job`, `processing_cost` |
| Processing queue | `app/services/processing_queue.py` | Priority queue, N workers; tiers `CHAT_PRIORITY` < `SESSION_PRIORITY` < `BACKLOG_PRIORITY`; dedup on `(kind, id)`; runners registered per kind (`register_runner`) |
| Ownership lock | `app/services/processing_ownership.py` | Postgres advisory lock on an AUTOCOMMIT connection, 30 s heartbeat; takeover steps registered (`register_takeover_sweep` before start, `register_takeover_requeue` after) |
| Media storage | `app/services/storage/` (`base`, `local`, `s3`, `multipart`) | Copied from Interview Intelligence. `STORAGE_BACKEND` `local` (development) or `s3` (`S3_BUCKET_NAME`); S3 uploads stream as multipart, one 8 MiB part in memory at a time, aborted on any failure. `copy_from_s3` copies a recording from the PMO folder server side (`CopyObject`; streamed to a file in development) |
| Recording checks | `app/services/media_files.py` | Shared by upload and URL download: extension in `ALLOWED_EXTENSIONS`, first bytes must match the extension's signature (WebM/Matroska, `ftyp` box, ID3 or MPEG frame, RIFF/WAVE, OggS), a running byte cap of `MAX_UPLOAD_SIZE_MB` on the bytes received, clean file names. A recording is stored at `sessions/<session id>/<name>` |
| Upload | `app/services/upload_service.py` | Streams the upload in 1 MiB chunks through the checks into storage; a refused or failed upload leaves nothing |
| URL download and SSRF guard | `app/services/url_download_service.py`, `app/services/url_guard.py` | HTTPS only. Every address the host resolves to must be public (no private, loopback, link-local or metadata, CGNAT, multicast or reserved address; IPv4-mapped IPv6 unwrapped), and the request goes to the checked address with the host name as Host and SNI, so TLS is verified against the name and a second DNS answer cannot redirect it. Redirects are followed by hand (at most `URL_DOWNLOAD_MAX_REDIRECTS`), each hop checked again. A pre-check reads headers only (HEAD, or a ranged GET when HEAD is refused); the download streams straight into storage through the recording checks, within `URL_DOWNLOAD_TIMEOUT_SECONDS` |
| Transcription | `app/services/transcription/assemblyai_client.py` | Submits the job, then polls its status every `ASSEMBLYAI_POLL_INTERVAL_SECONDS` under `ASSEMBLYAI_TIMEOUT_SECONDS`, so a timeout or shutdown stops cleanly. EU endpoint, `ASSEMBLYAI_SPEECH_MODELS`, speaker labels with 2–4 speakers expected (`ASSEMBLYAI_MIN_SPEAKERS`/`MAX_SPEAKERS`). Any failure is a `TranscriptionError` |
| Recordings scanner | `app/services/recordings/` (`folder_names`, `name_match`, `scanner`, `periodic`), `app/db/repositories/recording_repo.py` | Catalogs `RECORDINGS_SOURCE_BUCKET`/`RECORDINGS_SOURCE_PREFIX` and never processes anything; rules below |
| Sessions | `app/services/session_service.py`, `app/db/repositories/session_repo.py` | Creates sessions from a recording, an upload or a URL, and runs the `session` job; rules below |
| LLM factory | `app/ai/llm_factory.py` | Cached Azure OpenAI chat and embedding clients with a finite timeout (300 s) |
| Cost tracker | `app/services/cost_tracker.py` | Pure cost functions for LLM, embedding and transcription calls; AssemblyAI's hourly rate and diarization add-on are settings |
| Auth | `app/api/v1/auth.py`, `app/services/{auth,sso}_service.py` | Entra ID SSO (authorization code + PKCE, code exchanged by the backend; identity scopes only, no Microsoft token kept); members of the tenant with a role only (see the role model); local password auth only when `LOCAL_AUTH_ENABLED` (dev and CI), under the same role rule |
| Role grants | `app/services/user_roles.py`, `app/cli/user_role.py` | Grant, change or remove a role by email, or list users: the Admin "Users and roles" tab (`app/api/v1/users.py`) and, as a fallback, a one-off ECS task with `make user-role`. Both refuse to remove or change the role of the last active `pmo_manager` |
| Migrations | `alembic/versions/001_create_initial_schema.py`, `002_drop_user_ms_tokens.py`, `003_create_sessions_and_recordings.py`, `004_create_recording_scans.py` | Async Alembic; 001 enables pgvector and builds the Sprint 0 schema; 002 drops the stored Microsoft tokens from `users`; 003 adds the recordings catalog, sessions and transcripts; 004 the scan history (see "Data Model") |
| Admin commands | ECS task definition `<env>-admin-cli` (`infra/modules/environment/admin_cli.tf`) | The backend image with `DATABASE_URL`, run by `scripts/user-role.sh` in the backend's subnets and security group |
| Database bootstrap | `app/cli/db_bootstrap.py` | One-off ECS task per deployed environment: creates the `pmo_app` login (random password), makes it owner of the database and `public` schema, creates `vector`, and writes `DATABASE_URL` into the app secret. Idempotent; `--rotate-password` rotates. Run with `make db-bootstrap ENV=<env>` |

**Placement register** (owned here, BACKLOG #3):
- Edited by `pmo_manager` and `admin` only. A single placement is read by id under placement scope, like every by-id read.
- Unique: a client by its normalised name (case and spacing ignored), a consultant by email (any case), a project by (client, name), a placement by (consultant, project, start date). A duplicate answers 409.
- People named on a project or placement (tech lead, PS, SME) must be active users with a role, because being named gives scoped read of the placement.
- Nothing is deleted: a placement ends by `status` (`ended`, `terminated`, with `ended_reason`), a consultant by `left`.
- The CSV import applies these rules row by row inside one savepoint, plus its own: an empty cell keeps the stored value, people are existing users (never created), and a dry run, or a Confirm with any row error, writes nothing. Details in `docs/API.md`.

**Recordings scanner** (BACKLOG #2; the PMO folder `s3://nextcloud-talk-recordings-itc/recordings/pmo/` in the main ITC account):
- **What it reads**: a folder under the prefix is a recurring Talk room; a recording is a file with an allowed extension directly in it (nested files and other types are ignored). One recording is one call.
- **Earliest date** (`RECORDINGS_EARLIEST_DATE`, 2026-07-24): only calls on or after this UK date are cataloged, and a folder only when it holds one, so an older room still in use is kept with its recent calls only. A call's time is the one in its file name, else its S3 time. Set 2026-10-09, 2.5 months back; empty catalogs everything.
- **Folder names** (`folder_names.py`): a leading `DD-MM-YY` is the folder date, and a `#-#…` or `#|#…` routing suffix is dropped. Surveyed 2026-10-08: 79 of 310 names are dated; most read like `PRJ ITC BD – <name> – <client> – <start> – <end>`, with en dashes (U+2013) as separators.
- **Call time** (`recorded_at`): from `Recording YYYY-MM-DD HH-MM-SS` or `V1_YYYY-MM-DDTHHMMSS` (local time in `RECORDINGS_TIMEZONE`, Europe/London) or `screen-recording-<epoch ms>`. A name without one leaves it empty, and the S3 last-modified time stands in, marked as such. The zone was checked on the 2,424 Talk recordings: read as Europe/London none ends before it starts (median 22 min in summer, 20 in winter); read as UTC, 947 summer recordings would.
- **Matching** (`name_match.py`): a consultant is a candidate when the folder name (without date and suffix) holds the first or last token of their `full_name` as a whole word, ignoring case and accents. Every consultant counts, `left` included. One candidate is `matched`; among several, the only one with both names wins; otherwise `needs_choice` with the candidates. Each scan re-tries `unmatched` and `needs_choice` folders; `matched` and `chosen` folders are never changed.
- **Runs** (`periodic.py`): a scan is a processing-queue job (kind `recordings_scan`, one fixed id, backlog priority), so it never overlaps itself and only the processing owner runs it. Every task queues it at start and every `RECORDINGS_SCAN_INTERVAL_SECONDS` (900) when `RECORDINGS_SCAN_ENABLED` is set; "Scan now" (Phase 3 routes) queues the same job.
- **Scan history**: every pass writes a `recording_scans` row (counts, status, error). The catalog is one transaction, so a failed pass, or one past 600 s, changes nothing. A pass interrupted by a shutdown is failed by the next owner's takeover sweep.
- **Never processes**: the scan creates no session and queues no transcription; a person presses Process per recording.

**Sessions** (`session_service.py`):
- **From a recording** (Process): the folder must have a consultant (`matched` or `chosen`), and a recording becomes one session only. The session is held at the file's time (else its S3 time). Its placement is the folder consultant's one whose dates cover the call's UK date (`start_date` ≤ day ≤ `expected_end_date`, open-ended without one), whatever its status, since an ended placement still owns its old calls. When none or several do, the request answers 409 (`PlacementChoiceError`, with the placements to choose from: the covering ones, else all of the consultant's), and a `placement_id` of that consultant's may be given.
- **From an upload**: stored in the request (`sessions/<id>/<name>`); placement and `held_at` (with a time zone) come from the form.
- **From a URL**: checked in the request (headers only, SSRF guard), downloaded by the job.
- **The `session` job** (`SESSION_PRIORITY`): the caller commits, then queues the session (`enqueue_session`), since the worker opens its own database session. The job writes a `processing_jobs` row, sets the session `transcribing`, then by stage: `copying` (server-side copy into the media bucket) or `downloading`, and `transcribing` (AssemblyAI reads a two-hour presigned URL to the copy). It stores the transcript, the duration and a `processing_costs` row, and leaves the session `transcribed` for the analysis pipeline. Any failure sets the session and the job `failed` with the reason. A job for a session that is not `uploaded` does nothing.
- **Takeover**: sessions left `transcribing` or `analyzing`, and their `in_progress` jobs, are failed with "retry it"; sessions still `uploaded` are queued again.

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
- Roles are granted, changed and removed by a `pmo_manager` or `admin` on the Admin page ("Users and roles"), or with `make user-role ENV=<env> EMAIL=... ROLE=...` (`ROLE=none` removes one, `ARGS=--list` lists users) when nobody who can open the page can sign in. Granting a role to a new address creates the user; the last active `pmo_manager` keeps the role (409 on the page, exit 2 from the CLI).
- A denied by-id read answers 404, identical to a missing row, and logs a WARNING with user id and role.
- `BOOTSTRAP_ADMIN_EMAILS` raises listed users to `pmo_manager` at startup and at first sign-in (elevate-only).

## Frontend (as built)
Next.js 16.3.8 App Router app in `frontend/`, TypeScript strict, React 19.2, shadcn/ui, SWR, Tailwind 4. Packages via pnpm 12 (`packageManager: pnpm@12.6.0`; build-script approvals in `pnpm-workspace.yaml` `allowBuilds`). Node 22 or later.

| Area | Path | Notes |
|------|------|-------|
| Root layout | `src/app/layout.tsx` | Theme (light/dark/system), `AuthProvider`, `SWRProvider`, toasts; metadata from `APP_NAME` and `APP_TAGLINE` |
| Shell | `src/components/layout/{MainLayout,Sidebar,Header,ThemeToggle}.tsx` | Sidebar: Risk board, Actions, Admin (global roles only), Settings; header: app name, theme toggle, user menu with sign-out |
| Pages | `src/app/page.tsx` (Risk board), `actions/`, `admin/`, `settings/`, `login/`, `auth/callback/microsoft/` | Risk board, Actions and Settings are empty-state placeholders; Admin has the register, the import, users and roles, and the processing queue |
| Admin | `src/components/admin/AdminView.tsx` | Tabs Register, Import, Users and roles, Processing; the tab is in the URL (`?tab=`), and the page wraps the view in `Suspense` for `useSearchParams`. Other roles see a no-access message and no tabs, and nothing is requested |
| Register | `src/components/admin/register/` (`PlacementsTable`, `ConsultantsTable`, `ClientsTable`, `ProjectsTable`, their dialogs, `RecordDialog`, `fields`), `src/hooks/useRegister.ts`, `src/hooks/useUsers.ts`, `src/lib/register.ts` | Opens on Placements (status filter, search), with sub-tabs for Consultants, Clients and Projects; create and edit in dialogs (react-hook-form + zod); a failed save shows the API's message. `lib/register.ts` mirrors the register enumerations |
| Import | `src/components/admin/register/ImportTab.tsx` | Choose a CSV, Preview (dry run), then Confirm, enabled only after a preview with no row errors; per-row outcome, changes, warnings and errors; a template download |
| Processing | `src/components/admin/ProcessingStatusPanel.tsx`, `src/hooks/useProcessingStatus.ts` | Queue depth, running jobs by kind, backend memory; polls every 5 s while busy, 30 s when idle, and only while its tab is open |
| Users and roles | `src/components/admin/users/UsersTab.tsx`, `src/hooks/useUsers.ts`, `src/lib/roles.ts` (`ROLE_LABELS`) | Every user with role, account state and whether they have signed in with Microsoft yet, you marked; give access by email and role; change or remove a role, with the API's message shown (sessions ended, the last PMO manager refused) |
| Tables | `src/components/common/DataTable.tsx` | TanStack Table with sorting and a search box over every column, in the browser (the lists are small) |
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

**CI** (`.github/workflows/ci.yml`, on push and pull request to `main` and `develop`, and run by hand on `develop` to redeploy one side of staging):

| Job | Runs when | Steps |
|-----|-----------|-------|
| Detect Changes | always | A manual run takes its sides from the `target` input (backend, frontend or both) and fails on any branch but `develop`. Otherwise, path filters: backend, frontend, compose file; a change to `ci.yml` runs everything. A pull request compares with its base branch, a push to `main` with the previous commit, and a push to any other branch with `main`, so on `develop` everything not yet released counts as changed |
| Backend CI | `backend/**` changed | `uv sync --frozen`; ruff check; ruff format check; `mypy app` (strict); unit tests; integration tests (testcontainers starts pgvector) |
| Frontend CI | `frontend/**` changed | `pnpm install --frozen-lockfile`; eslint; `tsc --noEmit`; Prettier check; Vitest; `next build` |
| E2E Tests | backend, frontend or compose file changed | `docker compose up --build --wait`; `alembic upgrade head` from the runner; Playwright (Chromium) with local auth; stack logs on failure; report uploaded |
| Deploy to staging | push or manual run on `develop`, every job above passed or skipped, `vars.AWS_ROLE_ARN` set | See below |

- Checkout uses the default `GITHUB_TOKEN`, so there is no personal token to renew.
- The tools are pinned: uv `0.9.18`, pnpm from the `packageManager` field, Node 22. The actions are on their node24 majors.
- `make lint` runs the same lint gates as CI.

**Deploy** (the `deploy-staging` job in `ci.yml`):
- Only the side that changed since the previous commit on `develop` is rebuilt and redeployed. Redeploying the backend restarts processing, so a frontend-only push leaves it alone.
- **Manual redeploy**: `gh workflow run ci.yml --ref develop -f target=frontend` (or Actions > CI > Run workflow) rebuilds and redeploys the named side (`backend`, `frontend` or `both`) from the head of `develop`. It runs that side's checks and e2e first, so it still deploys only after CI passes. This replaces building an image by hand.
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
- **PMO recordings folder**: the backend's task role may list `nextcloud-talk-recordings-itc` under `recordings/pmo/` and read objects there; the bucket, in the main ITC account, grants the same to that role in its bucket policy (`docs/DEPLOYMENT.md`, section 9). Nothing in the main account is deleted or overwritten by this project.
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
| Transcription | AssemblyAI with speaker diarization on the EU endpoint (`api.eu.assemblyai.com`, Universal-3.5 Pro with a Universal-2 fallback); Teams' own transcript when a recording comes through Graph | Diarized utterances for the session pipeline | Reuse the shared AssemblyAI client |
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
- `processing_costs.session_id` and `message_id` have no foreign keys yet; they are added when `sessions` and `messages` arrive (`session_id` in migration 003).
- `access_log` carries `created_at`/`updated_at` as well as `at`; its index is on (`placement_id`, `at`).
- `consultants.status` defaults to `placed`; `placements.extension_status` defaults to `not_due` and `status` to `active`.
- Every enumerated column has a CHECK constraint built from `app/models/enums.py`.

**Built in migration 003 (Sprint 1)**: `recording_folders`, `source_recordings`, `sessions`, `session_transcripts`, and the foreign key `processing_costs.session_id` → `sessions` (`ON DELETE SET NULL`, so cost rows outlive a session). Differences from the draft above:
- `recording_folders` (new): `folder_key` (unique), `display_name`, `folder_date`, `consultant_id` (nullable), `match_status` (`matched` automatically, `chosen` by a person, `needs_choice`, `unmatched`), `candidate_consultant_ids` (JSONB), `last_seen_at`. The scanner re-matches only `needs_choice` and `unmatched` folders, so a person's choice is never overwritten.
- `source_recordings` (new): `folder_id`, `object_key` (unique), `size_bytes`, `last_modified`, `recorded_at` (from the file name, nullable).
- `sessions`: `kind` is nullable until the pipeline classifies the call or a person sets it. Added `kind_overridden_by_user_id`, `source_recording_id` (unique, so one session per recording; the recording finds its session through this column), `source_url` (URL sessions), `original_filename` (uploads and scanned files), `quotes_rejected` (count of signals dropped because their quote was not in the transcript) and `node_errors` (JSONB). Status defaults to `uploaded`.
- `session_transcripts`: `session_class` is the kind the classify node chose; `sessions.kind` holds the one in use.

**Built in migration 004 (Sprint 1)**: `recording_scans` (new): `started_at`, `finished_at`, `status` (`running`, `completed`, `failed`), `folders_seen`, `folders_added`, `folders_matched`, `recordings_seen`, `recordings_added`, `error_message`. One row per pass over the recordings folder.
