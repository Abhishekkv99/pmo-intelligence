# Sprint 1: Register and Sessions

**Status**: `in-progress` (plan approved 2026-10-08)
**Duration**: 2026-10-09 – 2026-10-22 (2 weeks)
**Objective**: PRD Phase 1. The placement register (admin pages, CSV import), session ingestion from the PMO recordings folder, upload and URL, transcription, the session pipeline with verified signals, and the session page. Also four Sprint 0 backlog items: drop the stored Microsoft tokens, debug off by default, the Admin "Users and roles" page, and a manual CI redeploy.
**Exit gate** (PRD Phase 1): three real recorded PMO calls processed end to end on staging, from consultants who were told beforehand that their call would be analysed; the PMO manager agrees the summary and signals are right.
**Source repo for copied code**: `E:\E Projects\Interview Intelligence Platform` (develop)
**Branch**: `develop`
**Previous sprint**: Sprint 0 (Bootstrap), complete 2026-10-08; see `docs/handover/sprint-00-handover.md`. Its plan, session notes and Decisions Log are in git history (`5434bec`).

---

## Research Findings Summary
- **PMO recordings folder** (read-only survey 2026-10-08):
  - Location: `s3://nextcloud-talk-recordings-itc/recordings/pmo/`, in the main ITC account `430006376054`, eu-west-2.
  - Contents: 309 folders and 2,433 recordings (2,428 webm, 4 mp4), 304 GiB in all, about 125 MiB per recording, about 75 recordings a month lately.
  - Encryption is SSE-S3 (no KMS grant needed). There is no bucket policy today.
  - **A folder is a recurring Nextcloud Talk room** with one `Recording YYYY-MM-DD HH-MM-SS.webm` per call.
  - Folder names follow `DD-MM-YY - <free text>#-#<ticket|ADHOC>#-#PMO#-#UK` (also with `#|#`). The free text mixes session tags (PMO support, PS, HC, FDC, PTP), stack codes (PRJ ITC DS), the consultant's name (first only, or full), the client and the placement dates. Some names show a mis-decoded dash (`�`), and one folder has an empty name.
- **Same region**: PMO's S3 gateway endpoint (default policy) reaches a bucket in another account in eu-west-2, so a server-side `CopyObject` works. Interview Intelligence streams copies only because its buckets are in different regions.
- **AssemblyAI**:
  - **EU endpoint**: `aai.settings.base_url = "https://api.eu.assemblyai.com"`. Data stays in the EU, at the same price as the US endpoint.
  - **`speech_models` is required.** The docs name the current model both `universal-3-pro` and `universal-3-5-pro`, so the value is configuration, confirmed by a smoke test.
  - **Pricing**: $0.21/hr for Universal-3.5 Pro, plus $0.02/hr for diarization. The cost tracker currently has $0.15.
  - **Diarization**: `speaker_labels`, plus `speakers_expected` or `speaker_options` (min and max).
  - **Open**: whether the PMO key works on the EU endpoint. Phase 1 smoke test.
- **LangGraph**:
  - The lock has 1.0.8. Version 1.2 (2026-05) added `add_node(timeout=, error_handler=)`, for async nodes only; how errors behave in a parallel fan-out is not documented.
  - Decision: stay on 1.0.x and enforce each node's timeout inside one shared node wrapper (`asyncio.timeout` plus try/except).
- **Structured output**: `with_structured_output(Model, method="json_schema", include_raw=True)`, as Interview Intelligence uses, with token usage read from the raw message.
- **Gaps in the copied Interview Intelligence code, to fix on copy**:
  - No evidence-quote verification.
  - No per-node timeout.
  - Meeting node failures and costs are never persisted.
  - URL download has no SSRF guard.
  - Upload size is checked only from `file.size`.
  - The scanner assumes one recording per folder.
- **Uploads**: recordings run to about 125–250 MiB, so stream them through the backend in 1 MiB chunks with a running byte cap. The 500 MB limit is already configured, and presigned browser uploads are not needed at this size.

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|
| Recordings (BACKLOG #2) | S3 folder `s3://nextcloud-talk-recordings-itc/recordings/pmo/` (main ITC account) | Upload and URL first; Teams meeting recordings; nowhere yet |
| System of record (#3) | Owned here: admin pages, plus a one-off CSV seed from the PS spreadsheet | Import and edit here too; external sync |
| Sprint scope | All of Phase 1 in one sprint | Phase 1 plus the Users page; split over two sprints |
| Transcription region | AssemblyAI EU endpoint | US endpoint (as Interview Intelligence) |
| S3 access | A bucket policy on the source bucket, applied by hand with the CLI under the main-account login (JSON and command in DEPLOYMENT.md); PMO's Terraform adds the matching task-role permission | A read role in the main account; a Terraform root for the bucket policy |
| Folder matching | A folder is matched to a consultant when its name contains their first or last name as a whole word (case- and accent-insensitive). A folder matching several consultants, or a consultant with several placements active on the date, needs a person to choose. Unmatched folders are not listed. **No auto-processing: a Process button per recording** | Triage inbox; naming convention; transcribe then match; list unmatched; substring match |
| Session unit | One recording file is one session, held at its file-name timestamp; the placement is the one active on that date | One folder is one session (the largest file) |
| Copy on Process | Server-side copy into PMO's media bucket (`sessions/<id>/`); AssemblyAI reads a presigned URL to the copy | Presign the source object |
| Scan trigger and kind | Catalog-only scan every 15 minutes (configurable) plus "Scan now"; the pipeline's classify node sets the session kind, and a person can correct it | Button only; the user picks the kind |
| SME scope (#5) | Decide at Sprint 2; Sprint 1 applies the existing placement-scope rule | PRD suggestion; SME sees everything in scope |
| Signals | `signals`, `issues` and `actions` tables now; the embedding column now, filled in Sprint 2 | Embed now; analysis JSON only |
| Consent for the gate calls (#6) | The three gate calls are from consultants told beforehand; who confirmed is recorded here. HR's notice still gates production | HR notice before the gate; internal staff calls |
| Backlog pulled in | Drop the stored Microsoft tokens; debug off by default; Admin "Users and roles" page; manual CI redeploy trigger | — |
| Permissions | `pmo_manager` and `admin`: register, CSV, users, scan, process, upload, URL. `sme`, `tech_lead`, `ps`: read the sessions of the placements naming them | Named roles may process; PMO manager only |
| CSV import | One row per placement; a dry-run preview, then Confirm; an unknown people email is a row error (import never creates users) | Create users without a role; one file per entity |
| Speaker roles | An LLM role-attribution node copied from Interview Intelligence, reframed for PMO roles, with the register's names as hints | AssemblyAI speaker identification |
| Session page extras | Audio player with jump-to-moment; kind override; retry; node errors panel | — |

## Task Checklist

### Phase 1: Backlog fixes and transcription smoke test
**Code work**
- [x] `backend/app/config.py`: `app_debug` defaults to `False`; compose and `.env.example` set `APP_DEBUG=true` for development (both already did; only the default changed; `tests/unit/test_config.py`)
- [x] Stop storing users' Microsoft tokens at sign-in (`services/sso_service.py`), remove `refresh_microsoft_token`; migration `002_drop_user_ms_tokens.py` drops `ms_access_token`, `ms_refresh_token`, `ms_token_expires_at`; `User` model updated (also: sign-in asks for `openid email profile` only, no `offline_access`, backend and `useSSOLogin.ts`; the app registration keeps the scope, unused; user decision 2026-10-08)
- [x] `.github/workflows/ci.yml`: `workflow_dispatch` with a `target` choice (backend / frontend / both) that redeploys that side of staging from `develop`; every `uses:` ref verified with `gh api` (no new refs; actionlint clean via Docker; runs that side's checks and e2e first, user decision 2026-10-08; fails on any branch but `develop`; first manual run after the push)
- [ ] Settings: `assemblyai_base_url` (EU default), `assemblyai_speech_models`, AssemblyAI prices as configuration; `cost_tracker` reads them
- [ ] Smoke test (not committed): the PMO key on the EU endpoint with a short public sample; record the key's region and the working `speech_models` value here
- [ ] Tests: config default, SSO without token storage, migration 002 up and down, AssemblyAI cost

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (users table, `> Status:`), `DEPLOYMENT.md` (manual redeploy, `> Status:`), `README.md` (redeploy row), `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`, `BACKLOG.md` (three items ticked)

**Commit checkpoints**
- [x] `fix: stop storing microsoft tokens at sign-in` (a2adca8)
- [x] `fix: default debug off outside development` (957636c)
- [ ] `ci: add a manual staging redeploy`

### Phase 2: Placement register, CSV import, Users and roles
**Code work**
- [ ] Repositories: `consultant_repo`, `client_repo`, `project_repo`, `placement_repo` (on `db/repositories/base.py`)
- [ ] `services/register_service.py`: CRUD, client `normalized_name`, validation (end after start, enumerations)
- [ ] `services/register_import.py`: CSV → per-row result (create / update / error); dry run; Confirm all-or-nothing in one transaction. Columns `consultant_full_name, consultant_email, client_name, project_name, client_manager_name, tech_lead_email, ps_email, sme_email, start_date, expected_end_date, extension_status, rate_band`. Dedup: clients on normalized name; consultants on email (else full name); projects on (client, name); placements on (consultant, project, start_date). Dates ISO or `DD/MM/YYYY`; UTF-8 with or without BOM; 1 MB, 1,000 rows at most
- [ ] Routes `api/v1/register.py` (global roles): list, create, update consultants, clients, projects, placements; `GET /placements/{placement_id}` with `require_placement_scope`; `POST /register/import?dry_run=`
- [ ] Routes `api/v1/users.py` (global roles): list, grant by email, change or remove a role, through `services/user_roles.py`; refuse to remove or change the last active `pmo_manager` (your own included)
- [ ] Frontend: Admin as tabs (Register, Import, Users and roles, Recordings, Processing); TanStack tables, create/edit dialogs (react-hook-form + zod); hooks `useRegister.ts`, `useUsers.ts`; `API_ROUTES` additions
- [ ] Tests: service, import (dry run, row errors, dedup, date formats, BOM, size), routes and guards (coverage test), integration against Postgres, frontend components

**Doc updates (concurrent)**
- [ ] `API.md` (register, import, users), `ARCHITECTURE.md` (register as built, Admin tabs, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick "Placement register"), `DEPLOYMENT.md` (`make user-role` stays as a fallback)

**Commit checkpoints**
- [ ] `feat: add the placement register with csv import`
- [ ] `feat: add the users and roles admin page`

### Phase 3: Sessions and ingestion (folder scanner, upload, URL, transcription)
**Code work**
- [ ] Migration `003_create_sessions_and_recordings.py`:
  - `sessions`, as in the ARCHITECTURE data model, plus `source_recording_id`, `kind_overridden_by_user_id`, `quotes_rejected` and `node_errors` (JSONB)
  - `session_transcripts`
  - `recording_folders`: `folder_key` (unique), `display_name`, `folder_date`, `consultant_id` (nullable), `match_status`, `candidate_consultant_ids` (JSONB), `last_seen_at`
  - `source_recordings`: `folder_id`, `object_key` (unique), `size_bytes`, `last_modified`, `recorded_at`, `session_id` (nullable)
  - a foreign key from `processing_costs.session_id`
- [ ] Copy and adapt from Interview Intelligence:
  - `services/storage/` (base, local, s3, multipart)
  - `services/transcription/assemblyai_client.py`: EU base URL, configured models, `speaker_options`, a timeout around the thread call
  - `upload_service.py`: running byte cap, extension plus magic-byte check, sanitised names
  - `url_download_service.py`: SSRF guard (https only; refuse private, loopback, link-local and metadata addresses; re-check every redirect hop; byte cap)
- [ ] `services/recordings/`:
  - `folder_names.py`: date, suffix strip (`#-#…`, `#|#…`), `�` repair, folding
  - `name_match.py`: whole word, first and last tokens of `full_name`
  - `scanner.py`: list, upsert folders and recordings, re-match unmatched and needs-choice folders, never process; time limit and claim
  - `periodic.py`: every `RECORDINGS_SCAN_INTERVAL_SECONDS` (900), run by the processing owner only
- [ ] `services/session_service.py`:
  - Create a session from a recording, an upload or a URL.
  - Status chain `uploaded → transcribing → transcribed → analyzing → completed / failed`.
  - Runner kind `session`: copy into PMO's bucket, transcribe, store the transcript and the AssemblyAI cost, then hand off to the pipeline (Phase 4).
  - Takeover sweep: sessions stuck in flight are marked failed.
  - Takeover requeue: waiting sessions are put back on the queue.
- [ ] Routes:
  - `api/v1/recordings.py` (global roles): list folders (matched, needs choice) with their recordings; `PUT /recording-folders/{folder_id}/consultant`; `POST /recordings/scan`; `POST /recordings/{recording_id}/process` (409 without `placement_id` when ambiguous).
  - `api/v1/sessions.py`: `POST /sessions/upload`, `POST /sessions/url` (global roles; placement chosen in the form).
- [ ] Settings `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX`, `RECORDINGS_SCAN_ENABLED`, `RECORDINGS_SCAN_INTERVAL_SECONDS`, `RECORDINGS_TIMEZONE` (Europe/London; checked against one recording with a known call time)
- [ ] Terraform (`infra/modules/environment/iam.tf`, `ecs.tf`, staging): task-role `s3:ListBucket` (condition `s3:prefix` `recordings/pmo/*`) and `s3:GetObject` on `nextcloud-talk-recordings-itc/recordings/pmo/*`; new env vars. Plan reviewed, applied on approval
- [ ] External step (user, main-account login): check `get-bucket-policy` (expected: none), then `put-bucket-policy` with the reviewed Allow-only JSON for PMO's staging task role
- [ ] Frontend:
  - Admin > Recordings tab: the folders table, a needs-choice picker, the recordings in each folder with a Process button (the confirmation shows the estimated cost), "Scan now" and the last scan time.
  - Upload and URL dialogs, from Interview Intelligence's `FileDropZone`, `UploadProgress` and `lib/upload.ts`.
- [ ] Tests:
  - Folder-name parser on the real name shapes.
  - Name matching: whole word, accents, ambiguity.
  - Scanner with mocked S3: new folders, new files in a matched room, nothing processed.
  - SSRF guard, upload cap, and the AssemblyAI mock.
  - Runner status chain and the sweeps.
  - Integration: migration 003 and the process flow.

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (ingestion and data model as built, `> Status:`), `API.md`, `DEPLOYMENT.md` (bucket policy JSON and command, env vars, `> Status:` from `terraform state list`), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick "Session ingestion")

**Commit checkpoints**
- [ ] `feat: add sessions and the recordings scanner`
- [ ] `feat: add session upload and url ingestion`
- [ ] `feat: grant the backend read on the pmo recordings prefix` (Terraform, after apply)

### Phase 4: Session pipeline and signals
**Code work**
- [ ] Migration `004_create_signals_issues_actions.py`:
  - `signals`: index on (`placement_id`, `occurred_at`), `embedding vector(1536)` nullable, `offset_ms`.
  - `issues` and `actions`.
- [ ] `app/ai/session/`:
  - `state.py`: `cost_records` and `node_errors` merged with `operator.add`.
  - `node.py`: one wrapper per node that times it, costs it, applies `asyncio.timeout` from configuration, and turns any exception into a `node_errors` entry.
  - `schemas.py`: the structured-output models.
  - `prompts/`: cite the enumerations constant.
  - `graph.py`: `attribute_roles → classify → summarise → [issues, relationship_engagement, client_signals, actions] → emit_signals`.
  - `attribute_roles` is given the register's names. `issues` and `actions` are given the placement's open items, so a repeated issue or a closing action names the earlier one. `emit_signals` is deterministic.
- [ ] Enumerations in `app/models/enums.py`: `SessionKind`, `SessionSource`, `SessionStatus`, `SpeakerRole`, `Dimension`, `Polarity`, `SourceKind`, `IssueStatus`, `ActionStatus`, `FolderMatchStatus`
- [ ] `services/quote_check.py`: normalise the quote (NFKC, casefold, quotes and dashes unified, whitespace collapsed), require it to be a substring of the transcript, then locate its utterance for `occurred_at` and `offset_ms`. Rejections are counted and never stored.
- [ ] Persistence:
  - On `session_transcripts`: the summary, `session_class` and `speaker_roles`.
  - The signals, issues and actions.
  - A `processing_costs` row per node, and one for AssemblyAI.
  - On the session: `node_errors` and `quotes_rejected`.
- [ ] Tests:
  - Each node with mocked responses, including the failure and timeout paths (non-fatal).
  - Quote rejection and quote location.
  - The graph end to end with mocks.
  - An integration run from transcript to signals.

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (pipeline as built, enumerations, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the session pipeline with verified signals`

### Phase 5: Session page and sessions list
**Code work**
- [ ] Session guards: `require_session_scope` / `require_logged_session_scope` (session → placement → scope; 404 on denial; the logged variant writes `access_log`). The coverage test requires one of them on any `{session_id}` path, and `require_roles` on `{recording_id}`, `{folder_id}` and `{user_id}` paths (the guard lands with the first session route in Phase 3)
- [ ] Backend `api/v1/sessions.py`:
  - `GET /sessions`: the sessions in the user's scope, filtered by consultant and status.
  - `GET /sessions/{session_id}` (logged): the session, with node errors for global roles.
  - `GET /sessions/{session_id}/media-url`: a 15-minute presigned URL.
  - `PATCH /sessions/{session_id}/kind` and `POST /sessions/{session_id}/retry` (global roles; retry resumes from the failed stage).
- [ ] Frontend:
  - `app/sessions/page.tsx`, with a "Sessions" sidebar entry.
  - `app/sessions/[sessionId]/page.tsx`:
    - Header: consultant, client, project, held at, kind (with override) and status. The page polls every 10 s while processing.
    - Audio player: clicking a signal, issue, action or transcript line seeks to that moment.
    - Summary, then the speaker-attributed transcript.
    - Signals with their quotes, then issues, actions and cost.
    - For global roles: the node errors panel and a retry button.
  - Hooks `useSessions.ts` and `useSession.ts`.
- [ ] Tests: guards and the access log, retry and override, components, e2e (a seeded completed session renders; the page polls while processing)

**Doc updates (concurrent)**
- [ ] `API.md`, `ARCHITECTURE.md` (frontend as built, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick "Session pipeline and session page")

**Commit checkpoint**
- [ ] `feat: add the session page and sessions list`

### Phase 6: Staging rollout, exit gate, audit and handover
**Code work and setup**
- [ ] Deploy through CI; Phase 3 Terraform applied on approval; bucket policy applied by the user
- [ ] First staging scan (catalog only); seed the register for the consultants concerned (CSV); resolve the needs-choice folders
- [ ] Exit gate: process three calls from consultants who were told (names and date recorded here); the PMO manager reviews summaries and signals; fixes made

**Doc updates (concurrent)**
- [ ] `docs/tracking/SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-01-handover.md`, `BACKLOG.md`, `ROADMAP.md`

**Commit checkpoints**
- [ ] `docs: record the sprint 1 exit gate`
- [ ] `docs: complete sprint 1 audit and handover`

## Blockers and Dependencies
- The PMO AssemblyAI key on the EU endpoint (Phase 1 smoke test). If the key is US-bound, an EU key is needed.
- A bucket policy on `nextcloud-talk-recordings-itc`, applied with the user's main-account login, before the staging scan (Phase 3/6).
- Register data for the consultants in the gate calls: a CSV from the PS team's spreadsheet.
- Three consultants told in advance that their calls will be analysed, and the PMO manager available for the review.

>>> CURRENT PHASE: Phase 1 — Backlog fixes and transcription smoke test (in progress)

## Session State (last updated: 2026-10-08 17:15)
- **Sprint**: 1 — Register and Sessions (PRD Phase 1)
- **Current phase**: Phase 1 — Backlog fixes and transcription smoke test (in progress)
- **Phase progress**: 3 of 6 Phase 1 code tasks complete
- **Last completed task**: manual staging redeploy (`workflow_dispatch`) in `ci.yml`; docs updated
- **Next task**: push Phase 1 commits (CI deploys the backend: migration 002 runs on staging), try a manual frontend redeploy; then AssemblyAI settings (EU base URL, models, prices) and the smoke test
- **Last commit**: 957636c "fix: default debug off outside development" (a2adca8 and 957636c not pushed); `ci: add a manual staging redeploy` follows
- **Uncommitted changes**: none after the redeploy commit
- **Blockers**: none yet (see Blockers and Dependencies)
- **Tests passing**: 293 unit + 48 integration (backend) + 88 frontend unit (2026-10-08 16:50) + 9 e2e (Sprint 0 close) = 438; ruff, mypy, eslint, typecheck, Prettier clean
- **Files created this session**: `backend/alembic/versions/002_drop_user_ms_tokens.py`, `backend/tests/unit/test_config.py`
- **Files modified this session**: `.github/workflows/ci.yml`, `README.md`, `docs/tracking/FEATURES.md`, `backend/app/config.py`, `backend/app/services/sso_service.py`, `backend/app/models/user.py`, `backend/tests/unit/test_sso_service.py`, `backend/tests/integration/test_migrations.py`, `frontend/src/hooks/useSSOLogin.ts`, `frontend/src/hooks/useSSOLogin.test.ts`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/planning/{CURRENT-SPRINT,BACKLOG}.md`, `docs/tracking/{CHANGELOG,FEATURES,TESTS}.md`
- **Key decisions this session**: Sprint 1 plan (User Decisions Made); `offline_access` dropped from sign-in requests, kept on the registration (Decisions Log)
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-00-handover.md`.
  - **Copying from Interview Intelligence**: code comes from `E:\E Projects\Interview Intelligence Platform`. Fix its known gaps on copy (see Research Findings).
  - **Local stack**: `make dev-build`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS sign-in**: `aws sso login --profile pmo-intelligence`. The source recordings bucket is read with the default profile (main account `430006376054`), read-only, until the bucket policy is applied.

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| One recording file is one session; a folder is a recurring Talk room matched to a consultant | Survey 2026-10-08: 309 folders hold 2,433 recordings; one session per folder would drop most calls |
| No automatic processing of scanned recordings; Process is a button per recording | User decision 2026-10-08; 2,433 recordings are on the folder, and Interview Intelligence's first scan once queued about 3,800 folders for paid processing |
| Name matching on the first and last tokens of `full_name`, whole word, case- and accent-insensitive; no new name columns | User decision 2026-10-08 (first or last name or both); whole-word matching keeps "Ann" from matching "Anna" |
| Recording file-name timestamps read as Europe/London (`RECORDINGS_TIMEZONE`) | Plan approval 2026-10-08; checked in Phase 3 against one recording with a known call time |
| Stay on LangGraph 1.0.x; timeouts enforced in one shared node wrapper | Plan approval 2026-10-08; 1.2's native node timeouts need async nodes, and their parallel fan-out behaviour is not documented |
| Evidence quotes checked by a normalised substring match against the transcript; an unverified signal is never stored, only counted | PRD ("Keep the model honest") and the project rules; Interview Intelligence had no check |
| By-id session routes use a session scope guard (session → placement → scope, 404); a session page view writes `access_log` | Server-side scope on every by-id route; session pages show a consultant's data |
| The Users page refuses to remove or change the last active `pmo_manager` | Plan approval 2026-10-08; prevents a lockout that only `make user-role` could undo |
| Sign-in requests identity scopes only (`openid email profile`); `offline_access` dropped from the authorize request and the code exchange, kept on the app registration | User decision 2026-10-08; with no Microsoft token stored, a refresh token has no use. Leaving the registration alone keeps existing consents and needs no Entra change. Alternatives offered: drop it from the registration too (re-run the script); keep requesting it |
| A manual redeploy re-runs the chosen side's checks and e2e before deploying | User decision 2026-10-08; keeps "deploy only after CI succeeds". Alternative offered: deploy straight away |
| AssemblyAI model names and prices are configuration | Plan approval 2026-10-08; the docs give two spellings for the current model and the prices differ from the tracker's |
