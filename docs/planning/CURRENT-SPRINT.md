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
  - Folder names: 79 of 310 follow `DD-MM-YY - <free text>#-#<ticket|ADHOC>#-#PMO#-#UK` (also with `#|#`); the other 231 have no date and no suffix, e.g. `PRJ ITC BD – <name> – <client> – <start> – <end>`. The free text mixes session tags (PMO support, PS, HC, FDC, PTP), stack codes (PRJ ITC DS), the consultant's name (first only, or full), the client and the placement dates. One folder has an empty name.
  - **Corrected 2026-10-08 (Phase 3)**: the "mis-decoded dash (`�`)" was the cp1252 console reading the AWS CLI output. Read with boto3, the keys hold 93 real en dashes (U+2013) and no U+FFFD, so there is nothing to repair; an en dash is a separator.
  - Files: 2,424 `Recording YYYY-MM-DD HH-MM-SS.webm`, plus `V1_YYYY-MM-DDTHHMMSS.mp4/.webm` (4), `screen-recording-<epoch ms>.webm` (3), one other name, one file nested four levels deeper and one empty folder marker.
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
- [x] `.github/workflows/ci.yml`: `workflow_dispatch` with a `target` choice (backend / frontend / both) that redeploys that side of staging from `develop`; every `uses:` ref verified with `gh api` (no new refs; actionlint clean via Docker; runs that side's checks and e2e first, user decision 2026-10-08; fails on any branch but `develop`; first manual run 2026-10-08, run 37770017665: frontend CI and e2e passed, backend CI skipped, only the frontend built and deployed)
- [x] Settings: `assemblyai_base_url` (EU default), `assemblyai_speech_models`, AssemblyAI prices as configuration; `cost_tracker` reads them (`["universal-3-5-pro", "universal-2"]`, $0.21/hr + $0.02/hr diarization; `.env.example` updated; staging uses the defaults, no infra change)
- [x] Smoke test (not committed): the PMO key on the EU endpoint with a short public sample; record the key's region and the working `speech_models` value here (2026-10-08: **the PMO key works on `api.eu.assemblyai.com`**; a 282 s two-speaker sample transcribed with `speaker_labels`, speakers A and B, with each of `universal-3-pro`, `universal-3-5-pro` and `["universal-3-pro", "universal-2"]`; the two Pro ids are distinct models (874 vs 870 words). The rate card lists only `universal-3-5-pro` and `universal-2`)
- [x] Tests: config default, SSO without token storage, migration 002 up and down, AssemblyAI cost

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (users table, `> Status:`), `DEPLOYMENT.md` (manual redeploy, `> Status:`), `README.md` (redeploy row), `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`, `BACKLOG.md` (three items ticked) (README: in the CI section, since the redeploy is not a make target)

**Commit checkpoints**
- [x] `fix: stop storing microsoft tokens at sign-in` (a2adca8)
- [x] `fix: default debug off outside development` (957636c)
- [x] `feat: configure transcription for the eu endpoint` (1e7e2f8, pushed; deviation: a fourth Phase 1 commit for the AssemblyAI settings, which the plan did not list as its own commit)
- [x] `ci: add a manual staging redeploy` (b3fe779; pushed with a2adca8 and 957636c, CI run 37769000185 green and deployed both sides: migration 002 ran on staging, no SQL echo in the migration log, the live login bundle asks for `openid email profile` only)

### Phase 2: Placement register, CSV import, Users and roles
**Code work**
- [x] Repositories: `consultant_repo`, `client_repo`, `project_repo`, `placement_repo` (on `db/repositories/base.py`) (`PlacementRow` loads a placement with its consultant, project, client and people in one joined query)
- [x] `services/register_service.py`: CRUD, client `normalized_name`, validation (end after start, enumerations) (plus uniqueness as 409 and the people rule; no delete, user decision 2026-10-08)
- [x] `services/register_import.py`: CSV → per-row result (create / update / error); dry run; Confirm all-or-nothing in one transaction. Columns `consultant_full_name, consultant_email, client_name, project_name, client_manager_name, tech_lead_email, ps_email, sme_email, start_date, expected_end_date, extension_status, rate_band`. Dedup: clients on normalized name; consultants on email (else full name); projects on (client, name); placements on (consultant, project, start_date). Dates ISO or `DD/MM/YYYY`; UTF-8 with or without BOM; 1 MB, 1,000 rows at most (filled cells overwrite, empty cells keep; people must be users with a role, a different role warns; user decisions 2026-10-08. A savepoint per file and one per row)
- [x] Routes `api/v1/register.py` (global roles): list, create, update consultants, clients, projects, placements; `GET /placements/{placement_id}` with `require_placement_scope`; `POST /register/import?dry_run=` (`PATCH` for updates, so CORS now allows `PATCH`; import rate-limited 10/min; always 200 with `applied`)
- [x] Routes `api/v1/users.py` (global roles): list, grant by email, change or remove a role, through `services/user_roles.py`; refuse to remove or change the last active `pmo_manager` (your own included) (`POST /users`, `PATCH /users/{user_id}`; the guard lives in `UserRoleService`, so `make user-role` refuses too, user decision 2026-10-08; a disabled manager does not count)
- [x] Frontend: Admin as tabs (Register, Import, Users and roles, Recordings, Processing); TanStack tables, create/edit dialogs (react-hook-form + zod); hooks `useRegister.ts`, `useUsers.ts`; `API_ROUTES` additions (register part done: tabs Register, Import, Processing with `?tab=`; Placements first with sub-tabs, user decision 2026-10-08; generic `DataTable`; `api.patch`. Users and roles tab added with its commit, with role names from `ROLE_LABELS`; the Recordings tab comes in Phase 3)
- [x] Tests: service, import (dry run, row errors, dedup, date formats, BOM, size), routes and guards (coverage test), integration against Postgres, frontend components (register part done: 13 unit, 30 integration, 20 frontend unit, 2 new e2e specs on the compose stack; users: 11 integration, 4 frontend unit, 1 e2e; e2e 12/12 on a cold backend, twice)

**Doc updates (concurrent)**
- [x] `API.md` (register, import, users), `ARCHITECTURE.md` (register as built, Admin tabs, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick "Placement register"), `DEPLOYMENT.md` (`make user-role` stays as a fallback) (also `README.md`, the `make user-role` row)

**Commit checkpoints**
- [x] `feat: add the placement register with csv import` (dc7c5ab; deviation: also brings `GET /users`, which the people pickers need)
- [x] (Discovered 2026-10-08) `fix: commit before the response is sent` (12da342): the request session (`get_db`, copied from Interview Intelligence) committed after the response, FastAPI's default for a yield dependency, so a list read straight after a save could miss the row (seen as flaky register e2e runs) and a failed commit still answered success. `DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]` at all 25 sites; `tests/unit/test_db_session_scope.py` (fails with the old scope); e2e 11/11 twice (user decision 2026-10-08)
- [x] `feat: add the users and roles admin page` (887f3b7; pushed with dc7c5ab and 12da342)

### Phase 3: Sessions and ingestion (folder scanner, upload, URL, transcription)
**Code work**
- [x] Migration `003_create_sessions_and_recordings.py` (models in `app/models/session.py`; user decisions 2026-10-08: match status `matched / chosen / needs_choice / unmatched`; the session links to its recording in one direction only, so `source_recordings` has no `session_id`; `sessions.kind` nullable until classified; `sessions.source_url` and `original_filename` added; the cost key is `ON DELETE SET NULL`. Deviation: `SessionKind`, `SessionSource`, `SessionStatus` and `FolderMatchStatus` land here, not in Phase 4, because the CHECK constraints need them; tests `test_session_schema.py` (10) and a 003 case in `test_migrations.py`):
  - `sessions`, as in the ARCHITECTURE data model, plus `source_recording_id`, `kind_overridden_by_user_id`, `quotes_rejected` and `node_errors` (JSONB)
  - `session_transcripts`
  - `recording_folders`: `folder_key` (unique), `display_name`, `folder_date`, `consultant_id` (nullable), `match_status`, `candidate_consultant_ids` (JSONB), `last_seen_at`
  - `source_recordings`: `folder_id`, `object_key` (unique), `size_bytes`, `last_modified`, `recorded_at` (no `session_id`: decided 2026-10-08)
  - a foreign key from `processing_costs.session_id`
- [x] Copy and adapt from Interview Intelligence (storage copied with its tests; the signature check, byte cap and file names shared in `services/media_files.py`; the SSRF guard in `services/url_guard.py`; URL downloads stream straight into storage, no temp file; the URL cap is `MAX_UPLOAD_SIZE_MB`; `aiofiles`, `assemblyai` and `botocore` added to mypy's ignore-missing-imports list, as `aioboto3` already was; user decisions 2026-10-08 in the Decisions Log; 113 unit tests):
  - `services/storage/` (base, local, s3, multipart)
  - `services/transcription/assemblyai_client.py`: EU base URL, configured models, `speaker_options`, a timeout around the thread call
  - `upload_service.py`: running byte cap, extension plus magic-byte check, sanitised names
  - `url_download_service.py`: SSRF guard (https only; refuse private, loopback, link-local and metadata addresses; re-check every redirect hop; byte cap)
- [x] `services/recordings/` (plus `db/repositories/recording_repo.py` and migration `004_create_recording_scans.py`; user decisions 2026-10-08 in the Decisions Log: the scan is a queue job, its history is a table, every consultant counts and the one full name wins, recordings are allowed files directly in the folder; the `�` repair was dropped, see Research Findings; checked read-only on the real folder: 2,432 recordings in 310 folders, 2,431 timed from the name; 34 unit and 9 integration tests):
  - `folder_names.py`: date, suffix strip (`#-#…`, `#|#…`), `�` repair, folding
  - `name_match.py`: whole word, first and last tokens of `full_name`
  - `scanner.py`: list, upsert folders and recordings, re-match unmatched and needs-choice folders, never process; time limit and claim
  - `periodic.py`: every `RECORDINGS_SCAN_INTERVAL_SECONDS` (900), run by the processing owner only
- [x] `services/session_service.py` (with `db/repositories/session_repo.py`, `copy_from_s3` on the storage backends, placement and recording lookups; user decisions 2026-10-09 in the Decisions Log; registered in `main.py` before takeover; 21 integration tests, 1 unit):
  - Create a session from a recording, an upload or a URL.
  - Status chain `uploaded → transcribing → transcribed → analyzing → completed / failed`.
  - Runner kind `session`: copy into PMO's bucket, transcribe, store the transcript and the AssemblyAI cost, then hand off to the pipeline (Phase 4).
  - Takeover sweep: sessions stuck in flight are marked failed.
  - Takeover requeue: waiting sessions are put back on the queue.
- [x] Routes (plus `services/recordings/catalog.py`, `schemas/recordings.py`, `middleware/body_limit.py`; the coverage test now requires `require_roles` on `{recording_id}`, `{folder_id}` and `{user_id}` paths, the role half of the Phase 5 coverage item; `held_at` stored in UTC; user decisions 2026-10-09 in the Decisions Log; 15 integration and 18 unit tests):
  - `api/v1/recordings.py` (global roles): list folders (matched, needs choice) with their recordings; `PUT /recording-folders/{folder_id}/consultant`; `POST /recordings/scan`; `POST /recordings/{recording_id}/process` (409 without `placement_id` when ambiguous).
  - `api/v1/sessions.py`: `POST /sessions/upload`, `POST /sessions/url` (global roles; placement chosen in the form).
- [x] Settings `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX`, `RECORDINGS_SCAN_ENABLED`, `RECORDINGS_SCAN_INTERVAL_SECONDS`, `RECORDINGS_TIMEZONE` (Europe/London; checked against one recording with a known call time) (`.env.example` too; `RECORDINGS_SCAN_ENABLED` defaults off and turns on the 15-minute loop only. The zone was checked on all 2,424 Talk recordings rather than one call: read as Europe/London none ends before it starts, medians 22 min summer and 20 min winter; read as UTC, 947 summer recordings would)
- [x] Terraform (`infra/modules/environment/iam.tf`, `ecs.tf`, staging) (applied 2026-10-09 after the cutoff was deployed (8ef7e9c, CI run 37833956860); a fresh plan shows no differences; 61 managed resources, unchanged. The first scan on staging: 49 of 310 folders with calls from 2026-07-24, 208 recordings, 0 matched (empty register). Written and planned 2026-10-09, `tfplan-recordings`: task-role statements `ListRecordingsFolder` and `ReadRecordings`, env vars `RECORDINGS_SOURCE_BUCKET`, `RECORDINGS_SOURCE_PREFIX`, `RECORDINGS_SCAN_ENABLED=true` on staging; 1 to add, 2 to change, 1 to destroy = the task definition replace, the service and the task policy. Approved; **held until the earliest-date cutoff is on staging**, user decision): task-role `s3:ListBucket` (condition `s3:prefix` `recordings/pmo/*`) and `s3:GetObject` on `nextcloud-talk-recordings-itc/recordings/pmo/*`; new env vars. Plan reviewed, applied on approval
- [x] External step (user, main-account login): check `get-bucket-policy` (expected: none), then `put-bucket-policy` with the reviewed Allow-only JSON for PMO's staging task role (2026-10-09: applied with the user's approval under their main-account login; `get-bucket-policy` showed none immediately before, the policy read back as approved; ownership is `BucketOwnerEnforced`, so it covers every object. Two statements for `arn:aws:iam::260172548683:role/pmo-intelligence-staging-ecs-task`: `s3:ListBucket` with `s3:prefix` `recordings/pmo/*`, `s3:GetObject` on `recordings/pmo/*`. Removal, if ever wanted, is the user's to run)
- [x] Frontend (user decisions 2026-10-09 in the Decisions Log: a recordings table with the choices above it, the estimate from size at a measured rate, the dialogs on the Recordings tab for any placement, polling while a session is in flight; the folder list gained `estimated_minutes`, `estimated_cost_usd` and the session's `error_message`; `ApiError` carries the body and a 204 resolves empty; 24 frontend unit tests, 2 e2e):
  - Admin > Recordings tab: the folders table, a needs-choice picker, the recordings in each folder with a Process button (the confirmation shows the estimated cost), "Scan now" and the last scan time.
  - Upload and URL dialogs, from Interview Intelligence's `FileDropZone`, `UploadProgress` and `lib/upload.ts`.
- [x] Tests (all listed below are in place; e2e 14/14 twice on the compose stack):
  - Folder-name parser on the real name shapes.
  - Name matching: whole word, accents, ambiguity.
  - Scanner with mocked S3: new folders, new files in a matched room, nothing processed.
  - SSRF guard, upload cap, and the AssemblyAI mock.
  - Runner status chain and the sweeps.
  - Integration: migration 003 and the process flow.

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (ingestion and data model as built, `> Status:`), `API.md`, `DEPLOYMENT.md` (bucket policy JSON and command, env vars, `> Status:` from `terraform state list`), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick "Session ingestion") (all done over the Phase 3 commits; `ROADMAP.md` ticked with the frontend commit)

**Commit checkpoints**
- [x] (Deviation, user decision 2026-10-08) `feat: add the session and recordings tables`: migration 003, models, tests and docs on their own, committed locally and pushed with the scanner commit
- [x] `feat: add sessions and the recordings scanner` (the scanner, migration 004 and the settings; pushed with 8629e82 and 43cb49b)
- [x] (Deviation, user decision 2026-10-08) `feat: add the recording storage, upload, url and transcription services`: the copied services and their tests on their own, committed locally, pushed with the scanner commit
- [x] (Deviation, user decision 2026-10-09) `feat: add the session service and its processing job`: the session service on its own, committed locally, pushed with the routes commit
- [x] `feat: add session upload and url ingestion` (the recordings and session routes; pushed with cc73e5e)
- [x] `feat: grant the backend read on the pmo recordings prefix` (Terraform, after apply)
- [x] (Discovered 2026-10-09, user decision) `feat: add the recordings tab and upload dialogs`: the frontend item, with the size-based estimate and the uploads directory fix; closes Phase 3

### Phase 4: Session pipeline and signals
**Code work**
- [ ] Migration `005_create_signals_issues_actions.py` (renumbered: 004 is the recording scans, Phase 3):
  - `signals`: index on (`placement_id`, `occurred_at`), `embedding vector(1536)` nullable, `offset_ms`.
  - `issues` and `actions`.
- [ ] `app/ai/session/`:
  - `state.py`: `cost_records` and `node_errors` merged with `operator.add`.
  - `node.py`: one wrapper per node that times it, costs it, applies `asyncio.timeout` from configuration, and turns any exception into a `node_errors` entry.
  - `schemas.py`: the structured-output models.
  - `prompts/`: cite the enumerations constant.
  - `graph.py`: `attribute_roles → classify → summarise → [issues, relationship_engagement, client_signals, actions] → emit_signals`.
  - `attribute_roles` is given the register's names. `issues` and `actions` are given the placement's open items, so a repeated issue or a closing action names the earlier one. `emit_signals` is deterministic.
- [ ] Enumerations in `app/models/enums.py` (`SessionKind`, `SessionSource`, `SessionStatus`, `FolderMatchStatus` already added with migration 003): `SpeakerRole`, `Dimension`, `Polarity`, `SourceKind`, `IssueStatus`, `ActionStatus`, `FolderMatchStatus`
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
- ~~The PMO AssemblyAI key on the EU endpoint~~ Resolved 2026-10-08: the key works on the EU endpoint.
- A bucket policy on `nextcloud-talk-recordings-itc`, applied with the user's main-account login, before the staging scan (Phase 3/6).
- Register data for the consultants in the gate calls: a CSV from the PS team's spreadsheet.
- Three consultants told in advance that their calls will be analysed, and the PMO manager available for the review.

>>> CURRENT PHASE: Phase 3 complete — next: Phase 4, Session pipeline and signals (not started)

## Session State (last updated: 2026-10-09 08:10)
- **Sprint**: 1 — Register and Sessions (PRD Phase 1)
- **Current phase**: Phase 3 — Sessions and ingestion; every task done, the frontend commit closes it
- **Phase progress**: 10 of 10 code tasks, tests and docs done
- **Last completed task**: Admin > Recordings tab with the upload and URL dialogs; e2e 14/14 twice
- **Next task**: check the CI run; then Phase 4 (session pipeline and signals) when the user says so
- **Last commit**: (pending) "feat: add the recordings tab and upload dialogs" (closes Phase 3; pushed, CI: pending)
- **Uncommitted changes**: none (just committed)
- **Blockers**: none; seeding the staging register (Phase 6) is what makes folders match
- **Tests passing**: 526 unit + 146 integration (backend) + 137 frontend unit + 14 e2e = 823 (2026-10-09); ruff, mypy, eslint, typecheck, Prettier clean; `next build` green
- **Files created this session**: Phase 3: `backend/alembic/versions/003_create_sessions_and_recordings.py`, `backend/app/models/session.py`, `backend/tests/integration/test_session_schema.py`, `backend/app/services/storage/*`, `backend/app/services/transcription/{__init__,assemblyai_client}.py`, `backend/app/services/{media_files,upload_service,url_download_service,url_guard}.py`, `backend/tests/unit/test_{assemblyai_client,media_files,multipart_upload,storage_local,storage_s3,upload_service,url_download_service,url_guard}.py`, `backend/alembic/versions/004_create_recording_scans.py`, `backend/app/services/recordings/{__init__,folder_names,name_match,scanner,periodic}.py`, `backend/app/db/repositories/recording_repo.py`, `backend/tests/unit/test_{folder_names,name_match,recordings_periodic}.py`, `backend/tests/integration/test_recordings_scanner.py`, `backend/app/services/session_service.py`, `backend/app/db/repositories/session_repo.py`, `backend/tests/integration/test_session_service.py`, `backend/app/api/v1/{recordings,sessions}.py`, `backend/app/schemas/recordings.py`, `backend/app/services/recordings/catalog.py`, `backend/app/middleware/body_limit.py`, `backend/tests/unit/test_body_limit.py`, `backend/tests/integration/test_recordings_api.py`, `backend/tests/unit/test_recordings_cutoff.py`, `frontend/src/components/admin/recordings/{RecordingsTab,RecordingsTab.test,dialogs,FilteredSelect}.tsx`, `frontend/src/components/common/{FileDropZone,UploadProgress}.tsx`, `frontend/src/hooks/useRecordings{,.test}.ts`, `frontend/src/lib/recordings{,.test}.ts`, `frontend/src/lib/upload.ts`, `frontend/src/types/recordings.ts`, `frontend/tests/e2e/admin-recordings.spec.ts`. Phase 2: `backend/app/db/repositories/{consultant,client,project,placement}_repo.py`, `backend/app/schemas/{register,users}.py`, `backend/app/services/{register_service,register_import}.py`, `backend/app/api/v1/{register,users}.py`, `backend/tests/unit/test_register_import_file.py`, `backend/tests/integration/test_register_{api,import}.py`, `frontend/src/components/admin/register/*`, `frontend/src/components/common/DataTable{,.test}.tsx`, `frontend/src/hooks/{useRegister,useUsers}.ts`, `frontend/src/hooks/useRegister.test.ts`, `frontend/src/lib/register{,.test}.ts`, `frontend/src/types/register.ts`, `frontend/tests/e2e/admin-register.spec.ts`
- **Files modified this session**: Phase 3: `backend/app/models/{enums,processing_cost,__init__}.py`, `backend/tests/integration/test_migrations.py`, `backend/app/config.py`, `backend/pyproject.toml`, `.env.example`, `backend/app/main.py`, `backend/app/models/session.py`, `backend/app/services/storage/{base,s3,local}.py`, `backend/app/db/repositories/{placement,recording}_repo.py`, `backend/tests/unit/test_storage_s3.py`, `infra/modules/environment/{iam,ecs,variables}.tf`, `infra/environments/staging/main.tf`, docs `DEPLOYMENT`, `backend/Dockerfile`, `backend/app/services/recordings/catalog.py`, `backend/app/schemas/recordings.py`, `frontend/src/components/admin/AdminView{,.test}.tsx`, `frontend/src/lib/{api,constants}.ts`, docs `planning/ROADMAP`, `backend/app/api/router.py`, `backend/tests/unit/test_entitlement_coverage.py`; docs `API`, `tracking/FEATURES`; docs `ARCHITECTURE`, `tracking/{TESTS,CHANGELOG}`, `planning/CURRENT-SPRINT`. Phase 2: `backend/app/api/router.py`, `backend/app/main.py` (CORS PATCH), `backend/app/db/repositories/user_repo.py`, `backend/app/services/user_roles.py` (id on `UserSummary`), `frontend/src/components/admin/AdminView{,.test}.tsx`, `frontend/src/app/admin/page.tsx`, `frontend/src/lib/{api,api.test,constants}.ts`; docs `API`, `ARCHITECTURE`, `planning/{CURRENT-SPRINT,ROADMAP}`, `tracking/{CHANGELOG,FEATURES,TESTS}`
- **Key decisions this session**: Phase 3: folder match status `matched / chosen / needs_choice / unmatched`; session → recording link one way (`sessions.source_recording_id`, unique); `sessions.kind` nullable; `source_url` and `original_filename` on sessions; migration 003 committed on its own; AssemblyAI submit-and-poll, 2–4 speakers, pinned SSRF guard, signature must match the extension; scan as a queue job, `recording_scans`, matching every consultant with the full name winning, recordings directly in the folder with a last-modified fallback; placement by covering dates with a choice when ambiguous, slow steps in the job with a job row, `held_at` required on forms, stop at `transcribed`; one nested folder list, any consultant choosable, 409 with choices, upload body limit; earliest date 2026-07-24 for the scan, Terraform apply held until it is deployed, nothing ever deleted or overwritten in the main account; recordings table with choices above, size-based estimate, dialogs on the tab, polling while in flight, uploads directory owned by `appuser` (Decisions Log). **Audit note (Rule C)**: local uploads had never worked: the compose volume at `/app/uploads` was root's and the backend runs as `appuser`, so the first write failed with 500. Unit and integration tests write to a temporary directory, so only an e2e upload through the real container showed it. Cause: the copied Dockerfile switched to a non-root user without preparing the volume's mount point. Rule to add: every path a non-root container writes to (volumes included) is created and chowned in the Dockerfile, and an e2e test writes through it. **Audit note (Rule C)**: `make dev-build && make migrate && make test-e2e` never got past the first step, because `dev-build` runs compose attached; found after the run sat for 27 minutes. Rule to add: chain only commands that return; start the stack detached (`docker compose up --build -d --wait`) when later steps depend on it. **Audit note (Rule C)**: FEATURES.md was in Phase 3's doc list but missed by the first three Phase 3 commits (8629e82, 43cb49b, 15df2ce); caught when the routes commit's doc list was re-read, and the Phase 3 rows were added then. Cause: the doc list was re-read only for docs the change obviously touched. Rule to add: before each commit, walk the phase's doc list item by item and either change the doc or note why not. Phase 2: CSV blanks keep; people are users with any role; no delete; Placements-first layout; commit before the response (Decisions Log). **Audit note (Rule C)**: the request session from Interview Intelligence committed after the response, FastAPI's documented default for yield dependencies; found only because a register e2e read its write back at once. Cause: copied infrastructure code was not checked against the framework's current semantics. Rule to add: a yield dependency that commits or releases a resource the response depends on is declared with `scope="function"`, and a test walks every route to check it. **Audit note (Rule C)**: two e2e flakes in this phase had test-side causes. The first import after a container restart is slow (cold backend), and back-to-back local runs exhaust the import's 10/minute limit, because every worker signs in as the one e2e user. Fixed with a 15 s allowance on the import steps. Rule to add: an e2e step that waits on a server-side job gets the cold-start allowance; when an e2e failure looks random, read the backend log for its status codes (429, 5xx) before changing the test
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
| AssemblyAI default models `["universal-3-5-pro", "universal-2"]`, cost $0.21/hr plus $0.02/hr diarization | User decision 2026-10-08 after the smoke test: the current rate-card model, with Universal-2 for a language 3.5 Pro does not cover. Alternatives offered: 3.5 Pro alone; `universal-3-pro` as Interview Intelligence (accepted by the API, not on the rate card) |
| CSV re-import: a filled cell overwrites, an empty cell keeps the stored value | User decision 2026-10-08; re-importing the same sheet changes nothing. Alternatives offered: blanks clear; create only |
| People named in the register (CSV and pages) are active users with any role; a role other than the column's is a warning | User decision 2026-10-08. Alternatives offered: matching role required; any user row |
| No delete in Sprint 1: placements end by status, consultants leave by status | User decision 2026-10-08; foreign keys are RESTRICT and history will hang off these rows. Alternative offered: delete when unreferenced |
| Register tab opens on Placements, with sub-tabs for Consultants, Clients and Projects; the Admin tab is in the URL | User decision 2026-10-08. Alternatives offered: four equal sub-tabs; separate pages |
| `GET /users` ships with the register commit; changing roles stays with the Users and roles commit | The register's people pickers need the user list |
| The request session commits before the response: `DbSession` with `scope="function"` on every route and guard | User decision 2026-10-08, after flaky e2e runs traced to commits after the response. Alternatives offered: an explicit commit in every write route; retries in the e2e tests |
| The last-PMO-manager guard is in `UserRoleService`, so the page and `make user-role` both refuse | User decision 2026-10-08; recovery still works by granting `pmo_manager` to someone, and through the bootstrap list. Alternative offered: page only |
| Both global roles (`pmo_manager`, `admin`) manage users, the `pmo_manager` role included | User decision 2026-10-08; the PRD gives both user and access admin. Alternatives offered: admins cannot touch managers; PMO manager only |
| Folder match status has four values: `matched` (automatic), `chosen` (a person picked), `needs_choice`, `unmatched`; the scanner re-matches only the last two | User decision 2026-10-08; a person's choice is never overwritten by the 15-minute scan. Alternatives offered: three values plus `consultant_chosen_by_user_id`; four values plus that column |
| A session links to its recording through `sessions.source_recording_id` (unique) only | User decision 2026-10-08; no circular foreign key, no two columns to keep in step, one session per recording enforced by the database. Alternative offered: both directions, as first planned |
| `sessions.kind` is NULL until the classify node or a person sets it | User decision 2026-10-08; an unclassified call is shown as such rather than as `other`. Alternative offered: default `other` |
| Sessions keep `source_url` (URL sessions) and `original_filename` (uploads and scanned files) | User decision 2026-10-08; every session keeps its source reference (PRD, Inputs). Alternatives offered: URL only; nothing beyond `recording_key` |
| `processing_costs.session_id` → `sessions` is `ON DELETE SET NULL` | Matches `processing_job_id`; cost history outlives a session the retention job may later delete |
| AssemblyAI: submit once, then poll asynchronously under `ASSEMBLYAI_TIMEOUT_SECONDS` (1800) every `ASSEMBLYAI_POLL_INTERVAL_SECONDS` (5) | User decision 2026-10-08; a timeout or shutdown stops cleanly with no thread left polling. `Transcript.get_by_id` blocks until done, so status is read with `assemblyai.api.get_transcript`. Alternative offered: the blocking call in a thread under `asyncio.timeout`, as Interview Intelligence |
| Diarization expects 2 to 4 speakers (`ASSEMBLYAI_MIN_SPEAKERS`, `ASSEMBLYAI_MAX_SPEAKERS`) | User decision 2026-10-08; a PMO call is the consultant and a PMO person, sometimes an SME or tech lead. Alternatives offered: no hint; 2 to 6 |
| The URL download pins the connection to the address it checked (Host and SNI keep the name, so TLS is verified against it) | User decision 2026-10-08; closes the DNS-rebinding gap. Checked live: a pinned HEAD to a public site verifies, and httpcore passes `sni_hostname` as the TLS `server_hostname`. Alternative offered: check, then let httpx resolve again |
| A recording's first bytes must match its extension's signature | User decision 2026-10-08; a renamed file is refused with the reason. Alternative offered: any allowed media signature |
| A scan is a processing-queue job (kind `recordings_scan`, one fixed id, backlog priority); the 15-minute loop and Scan now only enqueue it | User decision 2026-10-08; the queue's (kind, id) dedup stops overlapping passes, and only the processing owner's queue runs jobs, so no lock of its own. Alternative offered: a separate loop with an advisory lock, Scan now running inside the request |
| Every scan writes a `recording_scans` row (migration 004; the signals migration becomes 005) | User decision 2026-10-08; the Recordings tab shows the last scan's time, counts and error, across restarts. Alternatives offered: newest `last_seen_at` only; in memory |
| Folder matching considers every consultant, `left` included; among several candidates the only one with both first and last name wins | User decision 2026-10-08; old recordings belong to past placements. Alternatives offered: exclude `left`; no tie-break |
| A recording is a file with an allowed extension directly in its folder; its time comes from the `Recording …`, `V1_…` or `screen-recording-<ms>` name, else the S3 last-modified time stands in, marked on the page | User decision 2026-10-08, after the survey found 8 files outside the Talk naming. Alternatives offered: no fallback time; Talk names only |
| `RECORDINGS_SCAN_ENABLED` switches only the 15-minute loop; Scan now always queues a scan | Development cannot read the bucket, so the loop is off there; a scan run by hand records its failure in `recording_scans` instead of failing silently |
| A recording's placement: the folder consultant's placement whose dates cover the call's UK date, whatever its status; none or several → 409 with the choices, and any placement of that consultant may be chosen | User decision 2026-10-09; an ended placement still owns the calls held while it ran. Alternatives offered: active status only; refuse when none covers |
| The `session` job does the slow steps (copy, download, transcribe); the session is `transcribing` from the job's start, and a `processing_jobs` row records stage, timing and error | User decision 2026-10-09; the request answers quickly, and the job row feeds the node-errors panel and retry (Phase 5). Alternatives offered: no job row; copy or download inside the request |
| Upload and URL sessions take `held_at` (date and time, UK) from the form, required, prefilled from a Talk-style file name | User decision 2026-10-09. Alternative offered: the file name, else the upload time |
| Until the analysis pipeline exists the job stops at `transcribed`; Phase 4 adds the analysis step and re-queues `transcribed` sessions | User decision 2026-10-09. Alternative offered: mark `completed` for now |
| The route commits before queueing a session; the service never commits on the request's behalf | The worker opens its own database session and must see the row; as in Interview Intelligence |
| `GET /recording-folders` returns the listed folders with their recordings and the latest scan in one response | User decision 2026-10-09; about 2,400 recordings, filtered in the browser like the other admin tables. Alternative offered: recordings fetched per folder |
| Any consultant may be chosen for any folder (to settle a choice or correct a wrong match); the folder becomes `chosen`; no clearing | User decision 2026-10-09. Alternatives offered: candidates only on needs-choice folders; also allow clearing |
| Process answers 409 with the placement choices (`{detail, placements}`) | User decision 2026-10-09; the dialog shows them without another request. Alternative offered: detail only |
| A body-limit middleware refuses an oversized upload (413) as it arrives | User decision 2026-10-09; Starlette spools a multipart body to disk before the route runs, so the service's cap alone came too late. Alternatives offered: Content-Length check only; leave as is |
| Only calls on or after `RECORDINGS_EARLIEST_DATE` (2026-07-24, a UK date) are cataloged; a folder is kept when it holds at least one, with only those calls | User decision 2026-10-09: only folders from the last 2.5 months are of interest. Alternatives offered: a folder's first recording must be after the date (old rooms dropped entirely); a rolling 76-day window; all recordings of a kept folder |
| The Terraform apply waits until the cutoff is deployed | User decision 2026-10-09; the redeploy runs the first scan at once, which must already honour the cutoff. Alternative offered: apply now with the scan off |
| Nothing is ever deleted or overwritten in the main ITC account (`430006376054`); changes there are additive, approved, and preceded by a read showing nothing to replace; any undo is the user's | User instruction 2026-10-09, given when approving that the bucket policy be applied for them |
| The Recordings tab is one table of recordings, newest first, with the folders that name more than one consultant above it | User decision 2026-10-09; fewest clicks to process a call. Alternatives offered: a folders table with recordings in a dialog; expandable folder rows |
| Process shows a cost estimate from the file size at `RECORDINGS_BYTES_PER_SECOND` (79,000), computed on the backend | User decision 2026-10-09; measured read-only on the 204 Talk recordings since the earliest date (median 77.4 KiB/s). Alternatives offered: a nominal bitrate; no estimate |
| Upload recording and Add from URL live on the Recordings tab and take any placement (active first) and the UK call time, prefilled from a Talk-style name | User decision 2026-10-09. Alternatives offered: active placements only; the Sessions page later |
| The Recordings tab polls every 10 s while a session is in flight, 60 s otherwise, only while open | User decision 2026-10-09. Alternative offered: refresh on demand |
| The backend image creates `/app/uploads` owned by `appuser`; the local `upload_data` volume was recreated | Found by the new upload e2e: the volume was root's, so local uploads failed with 500 (seen as a network error, the 500 carrying no CORS headers). User approved recreating the empty local volume 2026-10-09 |
| AssemblyAI model names and prices are configuration | Plan approval 2026-10-08; the docs give two spellings for the current model and the prices differ from the tracker's |
