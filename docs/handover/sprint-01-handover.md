# Sprint 01 Handover Document

**Sprint Duration**: 2026-10-08 - 2026-10-09 (planned 2026-10-09 – 2026-10-22; closed early)
**Sprint Objective**: PRD Phase 1. The placement register (admin pages, CSV import), session ingestion from the PMO recordings folder, upload and URL, transcription, the session pipeline with verified signals, and the session page; plus four Sprint 0 backlog items (drop the stored Microsoft tokens, debug off by default, the Users and roles page, a manual CI redeploy).
**Audit Status**: PASSED — see `docs/tracking/SPRINT-AUDIT.md`

> **GATE**: This handover can ONLY be created AFTER the sprint audit is complete.

**Exit gate (PRD Phase 1): not run.** The gate was three real recorded PMO calls, from consultants told beforehand, processed end to end on staging and agreed by the PMO manager. The user dropped the gate calls (they are not tracked) and postponed the register import, so the sprint closed without it (user decision 2026-10-09). Everything the gate needs is built and deployed; **the session pipeline has not yet run on a real call**. ROADMAP Milestone 1 keeps its exit gate unticked.

## 1. What Was Achieved
- **Sprint 0 backlog**:
  - Sign-in stores no Microsoft token and asks for identity scopes only; migration 002 drops the token columns (`services/sso_service.py`, `alembic/versions/002_drop_user_ms_tokens.py`).
  - `APP_DEBUG` defaults to off (`app/config.py`).
  - A manual staging redeploy of one side, checks first (`.github/workflows/ci.yml`, `workflow_dispatch`).
  - The Admin "Users and roles" tab; the last active PMO manager keeps the role, on the page and in `make user-role` (`api/v1/users.py`, `services/user_roles.py`, `frontend/src/components/admin/users/UsersTab.tsx`).
- **Placement register** (BACKLOG #3, owned here): create and edit consultants, clients, projects and placements on the Admin page, with uniqueness, date and people rules and no delete (`services/register_service.py`, `api/v1/register.py`, `frontend/src/components/admin/register/`); a CSV import previewed as a dry run and confirmed all or nothing (`services/register_import.py`, `ImportTab.tsx`).
- **Writes commit before the response** (`DbSession`, `scope="function"`, `app/dependencies.py`), with a test over every route.
- **Recordings ingestion** (BACKLOG #2, the PMO folder in the main ITC account):
  - Media storage (local or S3, multipart, server-side copy), upload checks (signature must match the extension, running size cap), URL download behind an SSRF guard with a pinned connection, AssemblyAI on the EU endpoint with submit-and-poll (`services/storage/`, `services/{media_files,upload_service,url_download_service,url_guard}.py`, `services/transcription/assemblyai_client.py`).
  - The recordings scanner, a queue job every 15 minutes, cataloging only calls from `RECORDINGS_EARLIEST_DATE` (2026-07-24), matching folders to consultants by name and never processing (`services/recordings/`, migration 004). On in staging: 49 folders, 208 recordings.
  - Read access to the folder: a bucket policy on the main account's bucket (applied by the user) and the task-role statements by Terraform (`infra/modules/environment/{iam,ecs,variables}.tf`).
- **Sessions**: from a recording (placement by the call's UK date, or chosen), an upload or a URL; the `session` job copies or downloads, transcribes, stores transcript and cost, then analyses; takeover fails interrupted runs for retry and re-queues waiting ones (`services/session_service.py`, migration 003; routes in `api/v1/{recordings,sessions}.py`, upload body limit in `middleware/body_limit.py`).
- **Session pipeline with verified signals**: LangGraph `attribute_roles → classify → summarise → [issues, relationship_engagement, client_signals, actions] → emit_signals`; every node non-fatal, timed, costed and stopped after `SESSION_NODE_TIMEOUT_SECONDS`; every quote checked against the transcript, a missing one dropped and counted; signals, issues (linked across calls) and actions stored in one transaction (`app/ai/session/`, `services/{quote_check,session_analysis}.py`, migration 005).
- **Admin > Recordings tab**: the last scan and Scan now, folder choices, every recording with its estimate and status, Process, Upload recording and Add from URL (`frontend/src/components/admin/recordings/`).
- **Sessions list and session page** (every role, scoped): the list with filters; the page with a recording player, summary, transcript by speaker, signals with quotes, issues, actions and cost, each playing the recording from its moment; kind correction, retry and failed steps for the global roles; polling while processing (`frontend/src/app/sessions/`, `frontend/src/components/sessions/`, `services/session_view.py`). Session scope guards (404 outside scope; the page writes `access_log`) and recording playback (presigned S3 URL; a signed local media route) (`app/dependencies.py`, `services/media_token.py`).
- **Tests**: 624 backend unit, 201 integration, 157 frontend unit, 17 e2e = 999 (from 433 at Sprint 0's end). A development seed writes analysed sessions for the e2e suite (`app/cli/seed_e2e_session.py`).

## 2. What Was NOT Achieved
- **PRD Phase 1 exit gate**: not run. The three gate calls were dropped by the user and are not tracked; the session pipeline has never processed a real call. No backlog item (user decision); see Priority 1 below.
- **Staging register**: the PS team's CSV was postponed, so the staging register is empty, no recordings folder matches a consultant, and nothing can be processed from the scan. Moved to BACKLOG (Medium priority).
- **Folder choices on staging**: wait for the register.

## 3. Decisions Made
The full Decisions Log (about 80 rows, each with its alternatives) is in `docs/planning/CURRENT-SPRINT.md` at the commit that closes this sprint. The ones that shape later sprints:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| The register is owned here; seeded once from the PS team's CSV | BACKLOG #3 | Import and edit here too; external sync |
| A recordings folder is a recurring Talk room; one recording file is one session | The survey: 309 folders hold 2,433 recordings | One session per folder |
| No automatic processing: a Process button per recording; the scan only catalogs | 2,433 recordings in the folder; cost and consent | Process on scan |
| Only calls from 2026-07-24 are cataloged (`RECORDINGS_EARLIEST_DATE`) | Only the last 2.5 months matter | Rolling window; whole folders |
| Nothing is ever deleted or overwritten in the main ITC account; changes there are additive and approved | User instruction | — |
| AssemblyAI on the EU endpoint, `["universal-3-5-pro", "universal-2"]`, $0.21/h + $0.02/h diarization | Data in the EU; the rate card's current model | US endpoint; `universal-3-pro` |
| Analysis runs in the same `session` job; a run with nothing usable fails for retry | One job per call; an outage shows as a retryable failure | A separate job; always completed |
| Signals come from issues, relationship/engagement and client nodes, with a `Dimension` the model chooses; actions are not signals | The health model reads one table | Fixed dimension per node |
| `SpeakerRole` is the PRD's `messages.author_role` set | One enumeration for sessions and chat | The PRD's four session roles |
| Issues are linked across calls by short id (open, and resolved in the last 30 days) and reopened when raised again | The repeated-blocker trigger reads them | No linking until embeddings |
| Every quote, actions' and closed actions' included, must be found in the transcript | PRD "keep the model honest" | Keep unverified actions |
| Sessions are read through their placement's scope; only the session page writes `access_log` | Scope on every by-id route | Log the list and media URL too |
| Local playback through a signed media route; presigned URLs on S3 | An `<audio>` tag cannot send the Bearer token | No player locally; a static mount |
| Retry resumes from what is stored (transcript → analysis only) | No second AssemblyAI charge | Always from the start |
| SME scope (BACKLOG #5) decided at Sprint 2 | Health scores do not exist yet | PRD suggestion |
| Sprint 1 closes without its exit gate; the CSV import is postponed | User decision 2026-10-09 | Remove the gate; keep the sprint open |

## 4. Files Created / Modified
**199 files**: 150 added, 49 modified, none deleted (since `5434bec`, the Sprint 0 close).

| File | Action | Description |
|------|--------|-------------|
| `backend/alembic/versions/002_*` to `005_*` | Created | Drop the token columns; sessions and recordings; recording scans; signals, issues and actions |
| `backend/app/models/{session,signal,enums}.py` | Created / modified | The new tables and their enumerations with meanings |
| `backend/app/ai/session/`, `backend/app/ai/structured.py` | Created | The session pipeline and one structured-output call |
| `backend/app/services/storage/`, `transcription/`, `recordings/` | Created | Media storage, AssemblyAI client, the folder scanner |
| `backend/app/services/{register_service,register_import,user_roles,media_files,upload_service,url_download_service,url_guard,session_service,session_analysis,session_view,quote_check,media_token}.py` | Created / modified | Register, import, users, ingestion, sessions, analysis, reads, playback |
| `backend/app/db/repositories/{consultant,client,project,placement,recording,session,signal}_repo.py` | Created | Queries for the above |
| `backend/app/api/v1/{register,users,recordings,sessions}.py`, `app/schemas/{register,users,recordings,sessions}.py` | Created | Routes and their schemas |
| `backend/app/dependencies.py`, `app/utils/entitlements.py`, `app/middleware/body_limit.py`, `app/config.py`, `app/main.py` | Modified / created | `DbSession`, session and token guards, `list_scope`, upload limit, settings, registrations |
| `backend/app/cli/seed_e2e_session.py` | Created | Development-only e2e seed |
| `backend/tests/unit/` (25 new files), `backend/tests/integration/` (10 new files) | Created / modified | See `docs/tracking/TESTS.md` |
| `backend/Dockerfile`, `backend/pyproject.toml` | Modified | `/app/uploads` owned by `appuser`; mypy ignore list |
| `frontend/src/components/admin/{register,users,recordings}/`, `frontend/src/components/sessions/`, `frontend/src/components/common/{DataTable,FileDropZone,UploadProgress}.tsx` | Created | Admin tabs, sessions list and page, shared components |
| `frontend/src/app/sessions/`, `frontend/src/app/admin/page.tsx`, `frontend/src/components/admin/AdminView.tsx`, `frontend/src/components/layout/Sidebar.tsx` | Created / modified | Pages, tabs, the Sessions link |
| `frontend/src/hooks/{useRegister,useUsers,useRecordings,useSessions}.ts`, `frontend/src/lib/{register,recordings,sessions,upload,api,constants}.ts`, `frontend/src/types/{register,recordings,sessions}.ts` | Created / modified | Data hooks, enumeration mirrors, API client (`patch`, error bodies) |
| `frontend/tests/e2e/{admin-register,admin-users,admin-recordings,sessions}.spec.ts` | Created | E2E specs |
| `.github/workflows/ci.yml` | Modified | Manual redeploy (`workflow_dispatch`) |
| `infra/modules/environment/{iam,ecs,variables}.tf`, `infra/environments/staging/main.tf` | Modified | Read access to the PMO recordings prefix; scan settings |
| `.env.example`, `docs/*` | Modified | Every new setting; ARCHITECTURE, API, DEPLOYMENT, PRD-derived plan, tracking docs |

## 5. Environment Changes
- **New dependencies**: none (mypy's ignore list gained `aioboto3`, `aiofiles`, `assemblyai`, `asyncpg`, `botocore`, `pgvector`).
- **New environment variables** (all in `.env.example`; staging uses the defaults except the recordings source and scan): `ASSEMBLYAI_BASE_URL`, `ASSEMBLYAI_SPEECH_MODELS`, `ASSEMBLYAI_COST_PER_HOUR_USD`, `ASSEMBLYAI_DIARIZATION_COST_PER_HOUR_USD`, `ASSEMBLYAI_MIN_SPEAKERS`, `ASSEMBLYAI_MAX_SPEAKERS`, `ASSEMBLYAI_TIMEOUT_SECONDS`, `ASSEMBLYAI_POLL_INTERVAL_SECONDS`, `SESSION_NODE_TIMEOUT_SECONDS`, `SESSION_REASONING_EFFORT`, `SESSION_RESOLVED_ISSUE_LOOKBACK_DAYS`, `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX`, `RECORDINGS_SCAN_ENABLED`, `RECORDINGS_SCAN_INTERVAL_SECONDS`, `RECORDINGS_TIMEZONE`, `RECORDINGS_EARLIEST_DATE`, `RECORDINGS_BYTES_PER_SECOND`, `URL_DOWNLOAD_TIMEOUT_SECONDS`, `URL_DOWNLOAD_MAX_REDIRECTS`.
- **Configuration changes**: `APP_DEBUG` defaults to off; sign-in requests `openid email profile` only; CORS allows `PATCH`; the local `upload_data` volume was recreated (owned by `appuser`).
- **Infrastructure changes**:
  - Staging: migrations 002–005 applied by CI deploys; the backend task role reads `nextcloud-talk-recordings-itc/recordings/pmo/*`; `RECORDINGS_SCAN_ENABLED=true` with the source settings (Terraform applied 2026-10-09; 61 managed resources, unchanged).
  - Main ITC account (`430006376054`): a bucket policy on `nextcloud-talk-recordings-itc` granting the staging task role list and read on `recordings/pmo/` (applied by the user 2026-10-09; additive; `docs/DEPLOYMENT.md` section 9).

## 6. Known Issues / Bugs
- **The session pipeline has not run on a real call** (High): only mocked models and seeded data so far. The first real calls may surface prompt, timeout or cost issues.
- **The staging register is empty** (Medium): no folder matches a consultant, so nothing can be processed from the scan; BACKLOG.
- **Processing takeover waits about 6.5 minutes after every backend deploy** (Medium): 370–390 s on four deploys; the old task's lock appears to be freed by the dropped connection, not released. Jobs are not lost. BACKLOG (tech debt).
- **Frontend unit tests time out under load** (Low): one or two dialog tests pass Vitest's 5 s limit with the default worker count while the compose stack runs; all pass with `--maxWorkers=4`. BACKLOG.
- **Carried from Sprint 0**: the Teams items (tenant admin results, app availability, chat RSC state), branch protection, and mypy strict for the tests (BACKLOG).

## 7. Learnings
### What Went Well
- Asking before building: every design gap was put to the user with options, and about 80 decisions are recorded with their alternatives, so the next session needs no memory of this one.
- E2E tests against the real compose stack found what unit and integration tests could not: the commit-after-response race (S1-1), the root-owned uploads volume (S1-4) and the polling bug (S1-8).
- Read-only checks against real data before building: the folder survey, the time-zone check on 2,424 recordings, and the measured bytes-per-second for the cost estimate.
- Nothing was deleted or overwritten in the main ITC account.

### What Didn't Go Well
- The exit gate could not be run: it depended on register data and consenting consultants that were not lined up during the sprint.
- Several findings came from copied code and tooling assumptions rather than new code (S1-1, S1-4, S1-3).
- Two flaky tests were of the sprint's own making (S1-10, S1-13), and one answer about CI was given from memory (S1-14).

### Rules Added / Updated
16 rules in the local rules (code style 3, testing 5, infrastructure and tooling 5, sprint workflow 2, git workflow 1) and 14 Learnings Log lines; see section 8.

## 8. Post-Sprint Audit Findings
**Findings count**: 14 (11 recorded during the sprint, 3 found at its close: S1-12 to S1-14)
**Rules added**: 16

| What was wrong | Root cause | Rule added/updated |
|---------------|-----------|-------------------|
| S1-1: writes committed after the response | FastAPI's default for yield dependencies, in copied code | Code style: `scope="function"` for committing yield dependencies; check copied code against the framework |
| S1-2: random register e2e failures | Cold backend and the import's rate limit, test-side | Testing: cold-start allowance; read the backend log first |
| S1-3: dashes reported as mis-decoded | The cp1252 console's rendering | Infra and tooling: read non-ASCII data with a UTF-8 reader |
| S1-4: local uploads failed with 500 | Volume mount point not owned by the non-root user | Infra and tooling: create and chown writable paths; an e2e writes through them |
| S1-5: a chained make command hung 27 minutes | `dev-build` stays attached | Infra and tooling: chain only commands that return |
| S1-6: FEATURES.md missed by three commits | Doc list re-read only for obvious docs | Sprint workflow: walk the doc list before every commit |
| S1-7: 6.5-minute processing takeover after deploys | Lock freed by the dropped connection; logged as normal | Infra and tooling: read the deploy log through to ownership and record the wait |
| S1-8: no polling after a retry | SWR timer set only when the option changes | Code style: polling intervals that can be 0 live in state |
| S1-9: a TESTS.md row stale since Phase 3 | Route-parametrised file not recounted | Sprint workflow: recount every row |
| S1-10: flaky ordering test | Equal sort keys | Testing: distinct sort keys; code style: meaningful tie-breaks |
| S1-11: e2e against an old image | Service not rebuilt | Infra and tooling: rebuild before e2e |
| S1-12: Vitest timeouts under load | CPU contention | Testing: re-run alone and with fewer workers before calling it a regression |
| S1-13: an unnamed unit failure | Output cut to one line; a fixed-sleep test | Testing: no fixed sleeps; keep failure names |
| S1-14: a push described as deploying nothing | Deploy filter not read | Git workflow: read the deploy filter first |

## 9. Next Sprint Recommendations
### Priority 1 (Must Do)
- **Run the session pipeline on real calls** before Health v1 builds on its signals: seed the staging register (BACKLOG), settle the folder choices, process a few calls from consultants who know their calls are analysed (BACKLOG #6), and review the summaries, signals, cost and node errors with a PMO manager. Health scores built on unreviewed signals inherit any prompt problem.
- **Sprint 2 planning (PRD Phase 2, Health v1)**: decide BACKLOG #5 (SME scope, now that scores are next) and #7 (starting weights and thresholds); plan the signal embeddings (the column exists, empty), the scoring module, snapshots, triggers and flags, the risk board and the consultant page.
### Priority 2 (Should Do)
- Fix the processing takeover delay (BACKLOG tech debt): check the ECS stop timeout, SIGTERM handling in the lifespan and the lock release.
- The Teams items with the tenant admin (BACKLOG High), ahead of Phase 3.
### Priority 3 (Nice to Have)
- The Vitest timeouts (a worker cap or a higher timeout), mypy strict for the tests, branch protection.
