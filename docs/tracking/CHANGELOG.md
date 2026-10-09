# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Security
- Sign-in no longer stores users' Microsoft access and refresh tokens, and asks Microsoft for identity scopes only (`openid email profile`, no `offline_access`). Migration 002 drops `users.ms_access_token`, `ms_refresh_token` and `ms_token_expires_at`; the unused `refresh_microsoft_token` is removed.

### Fixed
- Writes are committed before the response is sent. The request session ended after the response (FastAPI's default for a yield dependency), so a 201 could reach the browser before its row was committed: a list read straight after a save sometimes missed the new row, and a failed commit would still have answered success. Every route now takes its session as `DbSession` (`scope="function"`).
- `APP_DEBUG` now defaults to off, so a backend container that does not set it (the migration container, a one-off ECS task) no longer echoes every SQL statement into its logs. Compose and `.env.example` turn it on for development.

### Added
- Placement register on the Admin page: create and edit consultants, clients, projects and placements. It opens on Placements (status filter, search), with sub-tabs for the rest, and create and edit dialogs that show the API's reason when a save is refused. Clients are unique by normalised name, consultants by email, projects by (client, name) and placements by (consultant, project, start date). Named people must be active users with a role. Nothing is deleted.
- Register CSV import (`POST /register/import`): one row per placement, previewed as a dry run and confirmed all or nothing. Filled cells overwrite and empty cells keep, so re-importing a sheet changes nothing. People are named by the email of an existing user with a role. The Import tab offers a template.
- Admin tabs (Register, Import, Users and roles, Processing), with the tab in the URL; the processing queue polls only while its tab is open.
- Users and roles tab on the Admin page (`GET /users`, `POST /users`, `PATCH /users/{user_id}`): give access by email and role (an address that has never signed in is added and linked at its first sign-in), change a role, or remove it, which ends the user's sessions. The last active PMO manager keeps the role, on the page (409) and in `make user-role`. Roles are shown by name ("PMO manager", "Placement specialist").
- `PATCH` allowed by CORS, for local development.
- Admin > Recordings tab: the last scan and Scan now, folders that name more than one consultant with a picker, every cataloged recording with its estimated length and cost and its status, Process (with a placement choice when the call's date is ambiguous), and Upload recording and Add from URL dialogs that take a placement and the call's UK time. The folder list now carries each recording's estimate (`RECORDINGS_BYTES_PER_SECOND`, measured at 79,000) and a failed session's reason.
- Staging reads the PMO recordings folder: a bucket policy on `nextcloud-talk-recordings-itc` (main ITC account) for the staging task role, the matching task-role permissions, and `RECORDINGS_SCAN_ENABLED=true` with the source settings on the backend (Terraform). The first scan cataloged 49 folders and 208 recordings.
- The recordings scan catalogs only calls on or after `RECORDINGS_EARLIEST_DATE` (2026-07-24, a UK date), and a folder only when it holds one; older calls are out of scope.
- Recordings and session API (Admin > Recordings): `GET /recording-folders`, `PUT /recording-folders/{folder_id}/consultant`, `POST /recordings/scan`, `POST /recordings/{recording_id}/process` (409 with the placement choices when the call's date is ambiguous), `POST /sessions/upload` and `POST /sessions/url`, for PMO managers and admins. An upload body over the size limit is refused with 413 as it arrives. The route-coverage test now also requires a role guard on recording, folder and user id routes.
- Session service: a session is created from a scanned recording (its placement is the one whose dates cover the call's UK date, or a person chooses), an upload or a URL, and the `session` job copies the recording into the media bucket server side or downloads it, transcribes it, and stores the transcript and its cost. Each run is recorded in `processing_jobs` with its stage. On takeover, interrupted sessions are failed for retry and waiting ones are queued again.
- Recordings folder scanner (off until `RECORDINGS_SCAN_ENABLED` is set): every 15 minutes it catalogs the PMO recordings folder (folders as Talk rooms, recording files with their call time) and ties each folder to a consultant by first or last name; a folder matching several consultants waits for a person, and nothing is processed. Each pass is recorded in `recording_scans` (migration 004). New settings: `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX`, `RECORDINGS_SCAN_ENABLED`, `RECORDINGS_SCAN_INTERVAL_SECONDS`, `RECORDINGS_TIMEZONE`.
- Recording ingestion services, not yet wired to a route or job: media storage (local or S3, multipart streaming), uploads streamed with a running size cap and a check that the file's first bytes match its extension, URL downloads behind an SSRF guard (HTTPS only, public addresses only, connection pinned to the checked address, every redirect re-checked), and AssemblyAI transcription that submits and polls with a real timeout, expecting 2 to 4 speakers. New settings: `ASSEMBLYAI_MIN_SPEAKERS`, `ASSEMBLYAI_MAX_SPEAKERS`, `ASSEMBLYAI_TIMEOUT_SECONDS`, `ASSEMBLYAI_POLL_INTERVAL_SECONDS`, `URL_DOWNLOAD_TIMEOUT_SECONDS`, `URL_DOWNLOAD_MAX_REDIRECTS`.
- Session and recordings tables (migration 003): `recording_folders` and `source_recordings` catalog the PMO recordings folder; `sessions` (one per recording at most, kind empty until classified) and `session_transcripts`; `processing_costs.session_id` now references `sessions`, and a session's cost rows outlive it. No route or job uses them yet.
- Transcription settings: AssemblyAI's EU endpoint by default (`ASSEMBLYAI_BASE_URL`), `ASSEMBLYAI_SPEECH_MODELS` (Universal-3.5 Pro with a Universal-2 fallback), and its prices as settings. Transcription cost is now $0.21/hr plus $0.02/hr for diarization (was a fixed $0.15/hr).
- Manual staging redeploy: run the CI workflow on `develop` with `target` set to backend, frontend or both; it runs that side's checks and e2e, then deploys.
- Backend skeleton: FastAPI app with security headers, CORS, rate limiting and a health endpoint.
- Sign-in with Microsoft Entra ID (authorization code + PKCE) and local password auth for development and CI; refresh-token rotation.
- Role entitlement: `pmo_manager`, `sme`, `tech_lead`, `ps`, `admin`.
  - Placement-scope guards answer 404 on denial and log every denial.
  - A route-coverage test fails the build for any unguarded route.
- Access log writer for reads of consultant data.
- Bootstrap PMO managers from `BOOTSTRAP_ADMIN_EMAILS` (elevate-only).
- Processing queue (chat, session and backlog priority tiers; runners registered per job kind) and processing ownership lock with heartbeat and registered takeover steps.
- Processing status endpoint for PMO managers and admins.
- Migration 001: users, refresh tokens, consultants, clients, projects, placements, processing jobs and costs, access log; pgvector enabled.
- Teams Graph access: certificate and app registration scripts, a chat-access verification script, and the Teams connector app package.
- Frontend skeleton (Next.js 16.3.8, React 19.2, shadcn/ui, SWR, dark mode): sign-in with Microsoft (PKCE), session restore through the refresh cookie, and a route guard.
- Sidebar with Risk board, Actions, Admin and Settings. Admin is shown to PMO managers and admins only; anyone else opening `/admin` sees a no-access message.
- Admin page with the processing queue: queue depth, running jobs by kind and backend memory.
- Risk board, Actions and Settings placeholder pages.
- Frontend tooling: Prettier, `typecheck`, `format` and `format:check` scripts; pnpm 12 pinned with `packageManager`; Node 22 or later.
- Frontend unit tests (Vitest) and Playwright end-to-end tests for sign-in.
- Project documentation: PRD, architecture, API, roadmap, backlog, sprint templates.
- Local stack with Docker Compose: PostgreSQL 16 with pgvector, backend and frontend, each with a health check.
- Backend Dockerfile (non-root, uv 0.9.18) and frontend Dockerfile (non-root, pnpm 12.6.0, Next.js standalone server bound to all interfaces); one `.dockerignore` per image.
- Makefile targets for the stack, migrations, tests (`test`, `test-e2e`), lint (ruff, mypy strict, eslint, typecheck, Prettier check) and formatting.
- Configurable host ports for the local stack (`PMO_API_PORT`, `PMO_WEB_PORT`; defaults 8000 and 3000) so it can run beside other projects.
- `.env.example` listing every backend setting with local defaults.
- CI on GitHub Actions: path-filtered backend and frontend checks, end-to-end tests against the compose stack, and a staging deploy from `develop` that runs only after the checks pass (skipped until the deploy variables are set).
- README with prerequisites, quick start and common commands.
- Terraform state bucket in the PMO sandbox account (`infra/bootstrap/`): versioned, encrypted, public access blocked, TLS-only; state locking with native S3 lock files.
- Deployment guide (`docs/DEPLOYMENT.md`): account access through SSO, tooling, bootstrap order, the app secret's keys, the database bootstrap, Azure OpenAI, credential expiry reminders, and rollback of an app deploy (image retag, migrations) and of Terraform state.
- Terraform for the shared stack (VPC, ECR, ECS cluster, GitHub OIDC deploy role, deny-deletion policy) and a reusable environment module, applied for staging at `pmo-intelligence-staging.itcapp.ai`: HTTPS load balancer, PostgreSQL 16, app secret, media bucket, SES identity and ECS services.
- Database bootstrap (`app/cli/db_bootstrap.py`, `make db-bootstrap ENV=staging`): a one-off ECS task that creates the `pmo_app` login, gives it the database, enables pgvector and writes `DATABASE_URL` into the app secret; idempotent, with optional password rotation.
- Terraform for PMO's own Azure OpenAI (`infra/azure/`): resource group and resource in Sweden Central with Data Zone Standard deployments of `gpt-5.4-mini` and `text-embedding-3-small` for staging.
- Credential expiry reminders: scheduled emails 30, 14 and 3 days before each recorded credential expiry (the Teams Graph certificate first).
- Sign-in limited to members of the InformationTech tenant who hold a role: guests are refused by the id-token `acct` claim, no account is created for anyone else at sign-in (bootstrap admins excepted), and a removed role ends sessions on refresh and within 15 minutes on open pages. The callback page shows why a sign-in was refused.
- `make user-role ENV=<env> EMAIL=... ROLE=...` (`ROLE=none` to remove, `ARGS=--list` to list): grants roles by email as a one-off ECS task until the Admin users page exists.
- Entra SSO app registration script (`scripts/entra/Register-SsoApp.ps1`): single-tenant app with Web redirect URIs, user consent (assignment optional), and a client secret per environment written straight into the app secret; staging sign-in configured, with its secret's expiry reminded.
