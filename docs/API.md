# API Documentation

## Base URL
- Development: `http://localhost:8000/api/v1`
- Staging: `https://pmo-intelligence-staging.itcapp.ai/api/v1`
- Production: `https://pmo-intelligence.itcapp.ai/api/v1`

All routes live under `/api/v1`. Authenticated routes take `Authorization: Bearer <access token>`.

## Access rules
Applied on the server for every route; the route-coverage test (`backend/tests/unit/test_entitlement_coverage.py`) fails the build for a route without a guard.

| Guard | Used for | Denied response |
|-------|----------|-----------------|
| `require_roles(...)` | Operations that address no placement (admin, queue status) | `403 {"detail": "Not authorised for this operation"}` |
| `require_placement_scope` | Routes addressed by a placement id | `404`, identical to a missing placement |
| `require_logged_placement_scope` | Routes that show a consultant's data; also writes an `access_log` row | `404`, identical to a missing placement |
| `require_session_scope` | Routes addressed by a session id: the session's placement must be in scope | `404`, identical to a missing session |
| `require_logged_session_scope` | The session page; also writes an `access_log` row for the session's placement | `404`, identical to a missing session |
| `require_media_token` | The one route reached without the Bearer token (the audio player's source on local storage): a 15-minute token naming the session | `404`, identical to a missing session |

A route addressed by a recording, recordings folder, user or Teams chat id (`{recording_id}`, `{folder_id}`, `{user_id}`, `{chat_id}`) must carry `require_roles(...)`: those rows belong to no placement, so only the global roles reach them. A route addressed by a session id (`{session_id}`) must carry a session-scope guard. A route reached without the Bearer token is listed as token-scoped and must carry a token guard. The coverage test checks all of this.

**Roles** are `pmo_manager`, `sme`, `cdm` (Consultant Director: the consultancy-side manager of the consultant; it replaced the PRD's `tech_lead` on 2026-10-11), `ps` and `admin`, defined in `backend/app/models/enums.py`.
- **Global roles** (`pmo_manager`, `admin`) read every placement.
- **Other roles** read only the placements that name them as PS or SME, and a CDM every placement of the consultants they manage (`consultants.cdm_user_id`).
- **No role** (`null`): cannot sign in at all (below), and would read nothing.

**Who may sign in**: an active member of the InformationTech tenant whose user row holds a role.
- `POST /auth/sso/microsoft/callback` answers **403** `{"detail": "Guest accounts cannot sign in to PMO Intelligence."}` for a guest (id-token claim `acct` not `0`, or missing), and **403** `{"detail": "Your account has not been given access to PMO Intelligence. Ask a PMO manager."}` for anyone without an active role. No row is created for an unknown account, except a bootstrap admin (`pmo_manager`).
- `POST /auth/login` (dev and CI only) answers the same 403 for a correct password without a role.
- `POST /auth/refresh` answers **401** `{"detail": "Your session has ended. Please sign in again."}`, clears the cookie and revokes every refresh token of the user, once the role is removed or the account disabled.
- Every authenticated route answers **401** with the same message for such a user, so access ends within the 15-minute access-token life.

## Implemented Endpoints

### Health
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/health` | Public, not rate-limited | `{"status": "healthy", "service": "pmo-intelligence-api"}` |

### Auth
| Method | Path | Auth | Rate limit | Request | Response |
|--------|------|------|-----------|---------|----------|
| POST | `/auth/register` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 3/min | `{email, password (8–128), full_name}` | `201` `UserResponse` |
| POST | `/auth/login` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 5/min | `{email, password}` | `TokenResponse`; sets the `refresh_token` httpOnly cookie. 403 without a role |
| POST | `/auth/refresh` | `refresh_token` cookie | 10/min | — | `TokenResponse`; rotates the cookie. 401 once the role is removed or the account disabled |
| POST | `/auth/logout` | Bearer | — | — | `{message, revoked_tokens}`; clears the cookie |
| GET | `/auth/me` | Bearer | — | — | `UserResponse` |
| GET | `/auth/sso/microsoft/config` | Public | — | — | `{client_id, tenant_id, authority, redirect_uri}` |
| POST | `/auth/sso/microsoft/callback` | Public | 10/min | `{code, code_verifier, redirect_uri}` | `TokenResponse`; sets the refresh cookie. 403 for a guest or a user without a role |

- **`UserResponse`**: `{id, email, full_name, is_active, auth_provider, role, created_at}`. `role` is one of the roles above, or `null`.
- **`TokenResponse`**: `{access_token, token_type: "bearer"}`. The access token lasts 15 minutes; the refresh cookie lasts 7 days.

### Processing
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/processing/status` | `pmo_manager` or `admin` | `{queue_depth, capacity, running: [{kind, id, started_at, worker}], rss_mib, memory_diagnostics_enabled}` |

### Register
PMO managers and admins edit the register; any other role gets `403 {"detail": "Not authorised for this operation"}`. Updates are `PATCH`: only the fields sent change, and `null` clears a nullable field (a required field sent as `null` is a 422). Nothing is deleted: a placement ends by `status`, a consultant leaves by `status`.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/consultants` | `pmo_manager`, `admin` | — | `ConsultantResponse[]`, by name |
| POST | `/consultants` | `pmo_manager`, `admin` | `{full_name, email?, phone?, skills?, status?, cdm_user_id?}` | `201` `ConsultantResponse`; 409 if the email is taken (any case) |
| PATCH | `/consultants/{consultant_id}` | `pmo_manager`, `admin` | any of the above | `ConsultantResponse` |
| GET | `/clients` | `pmo_manager`, `admin` | — | `ClientResponse[]` |
| POST | `/clients` | `pmo_manager`, `admin` | `{name, industry?}` | `201` `ClientResponse`; 409 if the name exists (ignoring case and spacing) |
| PATCH | `/clients/{client_id}` | `pmo_manager`, `admin` | any of the above | `ClientResponse` |
| GET | `/projects` | `pmo_manager`, `admin` | — | `ProjectResponse[]`, by client then project |
| POST | `/projects` | `pmo_manager`, `admin` | `{client_id, name, client_manager_name?, start_date?}` | `201` `ProjectResponse`; 409 if the client already has the name |
| PATCH | `/projects/{project_id}` | `pmo_manager`, `admin` | any of the above | `ProjectResponse` |
| GET | `/placements` | `pmo_manager`, `admin` | — | `PlacementResponse[]`, newest start first |
| POST | `/placements` | `pmo_manager`, `admin` | `{consultant_id, project_id, start_date, expected_end_date?, extension_status?, rate_band?, stack?, ps_user_id?, sme_user_id?, status?, ended_reason?}` | `201` `PlacementResponse`; 409 if the consultant already has a placement on the project from that day |
| GET | `/placements/{placement_id}` | placement scope | — | `PlacementResponse`; 404 outside scope. An SME gets `extension_status`, `rate_band` and `ended_reason` as `null` |
| PATCH | `/placements/{placement_id}` | `pmo_manager`, `admin` (and placement scope) | any of the above | `PlacementResponse` |
| POST | `/register/quick-add?dry_run=true` | `pmo_manager`, `admin`; 10/min | `{lines: [string]}` (1 to 200 lines, each at most 500 characters) | `QuickAddResult` (below) |

- **Health**: creating or editing a placement, editing a project (its active placements) and an applied quick add (the placements it created or changed) queue a health recompute after the write commits; the answer does not wait for it.
- **Rules (422)**: `expected_end_date` not before `start_date`; a referenced client, consultant or project must exist; a named person (`cdm_user_id`, `ps_user_id`, `sme_user_id`) must be an active user who holds a role, since being named gives that user scoped read of the placement.
- **`PersonRef`**: `{id, full_name, email}`.
- **`ConsultantResponse`**: `{id, full_name, email, phone, skills, status, cdm: PersonRef | null, created_at, updated_at}`; `status` is `bench | placed | left`; `cdm` is the Consultant Director who manages the consultant (one CDM manages several consultants).
- **`ClientResponse`**: `{id, name, industry, created_at, updated_at}`.
- **`ProjectResponse`**: `{id, client_id, client_name, name, client_manager_name, start_date, created_at, updated_at}`.
- **`PlacementResponse`**: `{id, consultant: {id, full_name, email}, client: {id, name}, project: {id, name}, start_date, expected_end_date, extension_status, rate_band, stack, status, ended_reason, ps, sme, cdm, created_at, updated_at}`; `cdm` is the consultant's CDM; `stack` is the consultant's stack on this engagement (`DS`), free text up to 50 characters, and is given to an SME too; `extension_status` is `not_due | due | requested | confirmed | declined`, `status` is `active | ended | terminated`, and `ps`, `sme`, `cdm` are `PersonRef | null`.

**Quick add** (`POST /register/quick-add`): placements entered as lines in the Teams chat name format. The CSV import (`POST /register/import`) was removed 2026-10-11.
- **Line format**: `PRJ ITC <stack> - <consultant> - <client> - <start> - <end>`, e.g. `PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027`. The separator is a hyphen or an en dash with spaces around it; dates are `D/M/YYYY` or `D-M-YY`; the end is not before the start. `PRJ ITC` is read in any case and spacing is tidied. Any other form is an error on that line, with the reason. Blank lines are skipped; a body with none answers **422**.
- **Matching**: the client on its normalised name, else created; the consultant on full name (case and spacing ignored), else created with no email and status `placed` (two consultants with that name are an error on the line); the placement on (consultant, client, start date) across the client's projects, so renaming its project keeps it.
- **Writes**: a new placement goes under the client's project "To be confirmed" (created when missing), with the stack, the dates, `not_due` and `active`. An existing one gets the line's end date and stack when they differ, else it is unchanged; pasting a line twice changes nothing. Lines apply in order, so one line's new client is found by the next.
- **All or nothing**: `dry_run=true` (the default) never writes. `dry_run=false` writes every line, or none when any line has an error. The answer is **200** either way; `applied` says whether it wrote.
- **`QuickAddResult`**: `{dry_run, applied, summary: {lines, created, updated, unchanged, errors}, lines: [{line, text, outcome, stack, consultant, client, start_date, expected_end_date, changes, errors}]}`. `line` is the position among the lines sent, from 1; `outcome` is `create` (a new placement), `update`, `unchanged` or `error`; the parsed fields are `null` on a line that could not be read.

### Users
| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/users` | `pmo_manager`, `admin` | — | `UserListItem[]`, by email; no tokens, no Entra ids |
| POST | `/users` | `pmo_manager`, `admin` | `{email, role}` | `RoleChangeResult`; creates the user when the address has never signed in (linked at their first Microsoft sign-in); 422 for an invalid address |
| PATCH | `/users/{user_id}` | `pmo_manager`, `admin` | `{role}`, a role or `null` to remove it | `RoleChangeResult`; removing a role revokes every refresh token of the user; 404 for an unknown id |

- **`UserListItem`**: `{id, email, full_name, role, is_active, signed_in_with_microsoft}`.
- **`RoleChangeResult`**: `{user: UserListItem, message}`; `message` says what changed in words (sessions ended, or that a bootstrap admin will be raised again at their next sign-in).
- **The last active PMO manager keeps the role**: removing or changing it answers **409** `{"detail": "<email> is the last active PMO manager; make someone else a PMO manager first"}`. `make user-role` refuses the same change.

### Recordings
The PMO recordings folder (Admin > Recordings). PMO managers and admins only; any other role gets `403 {"detail": "Not authorised for this operation"}`. The scan catalogs the folder and never processes anything; a session is made only when a person presses Process.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/recording-folders` | `pmo_manager`, `admin` | — | `RecordingFolderList` (below): folders that are `matched`, `chosen` or `needs_choice` (unmatched ones are not listed), newest folder date first, each with its recordings |
| PUT | `/recording-folders/{folder_id}/consultant` | `pmo_manager`, `admin` | `{consultant_id}` | `204`; the folder becomes `chosen` and later scans keep it. Any consultant in the register may be chosen, to settle a folder or correct a wrong match; sessions already made keep their placement. 404 for an unknown folder, 422 for an unknown consultant |
| POST | `/recordings/scan` | `pmo_manager`, `admin`; 10/min | — | `202 {queued}`; `queued` is false when a scan is already waiting to start. Asked for while a scan runs, another runs after it (`queued` true) |
| POST | `/recordings/{recording_id}/process` | `pmo_manager`, `admin`; 30/min | `{placement_id?}` | `202` `SessionCreated`; the session's job is queued. 409 `PlacementChoice` (below) when no single placement covers the call; 409 `{detail}` when the folder has no decided consultant, or the recording is already a session; 422 for a placement that is not the folder consultant's; 404 for an unknown recording |

- **`RecordingFolderList`**: `{folders: [RecordingFolderItem], latest_scan: ScanSummary | null, scan_enabled, scan_interval_seconds}`.
- **`RecordingFolderItem`**: `{id, display_name, folder_date, match_status, consultant: {id, full_name} | null, candidates: [{id, full_name}], last_seen_at, recordings: [RecordingItem]}`. `display_name` is the folder name without its routing suffix; `folder_date` comes from a leading `DD-MM-YY`.
- **`RecordingItem`**: `{id, filename, size_bytes, recorded_at, time_from_name, estimated_minutes, estimated_cost_usd, session: {id, status, error_message} | null}`. `recorded_at` comes from the file name; when `time_from_name` is false it is the file's S3 time instead. The estimates come from the size at `RECORDINGS_BYTES_PER_SECOND` (79,000, measured on the PMO recordings) and the AssemblyAI rate: a guide before Process, not a quote. `error_message` says why a failed session failed.
- **`ScanSummary`**: `{id, started_at, finished_at, status, folders_seen, folders_added, folders_matched, recordings_seen, recordings_added, error_message}`; `status` is `running | completed | failed`.
- **Which placement**: the folder consultant's placement whose dates cover the call's UK date (`start_date` ≤ day ≤ `expected_end_date`, open-ended without one), whatever its status.
- **`PlacementChoice`** (409): `{detail, placements: [{id, client_name, project_name, start_date, expected_end_date, status}]}`: the covering placements when several cover the call, else every placement of the consultant. Send one back as `placement_id`.
- **`SessionCreated`**: `{id, placement_id, source, status, held_at}`; `source` is `s3 | upload | url | graph`, `status` starts at `uploaded`.

### Teams chats
The PMO group chats (Admin > Teams). PMO managers and admins only; any other role gets `403 {"detail": "Not authorised for this operation"}`. Discovery finds the chats titled `PRJ ITC …` in the PMO accounts' chat lists (titles only) and ties each to its placement from its title; here a person settles the rest. Nothing on this page reads a message.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/teams/chats` | `pmo_manager`, `admin` | — | `TeamsChatList` (below): every chat, by title |
| POST | `/teams/scan` | `pmo_manager`, `admin`; 10/min | — | `202 {queued}`; `queued` is false when a pass is already waiting to start. **409** `{"detail": "Teams discovery is off on this environment"}` while `TEAMS_DISCOVERY_ENABLED` is off |
| PUT | `/teams/chats/{chat_id}/placement` | `pmo_manager`, `admin` | `{placement_id}` | `204`; the chat becomes `chosen` and later passes keep it; its consultant member is looked for again; its watch review is queued. 404 for an unknown chat, 422 for an unknown placement |
| POST | `/teams/chats/{chat_id}/placement` | `pmo_manager`, `admin`; 10/min | `{line}`, one quick add line (1–500 characters; `quick_add_line` prefilled, maybe edited) | `QuickAddResult` (see "Register"), always 200: when `applied`, the placement the line found or created is linked (`chosen`), and its health recompute and the chat's watch review are queued; otherwise nothing is written and the line's `errors` say why. 404 for an unknown chat |
| PUT | `/teams/chats/{chat_id}/consultant-member` | `pmo_manager`, `admin` | `{oid}`, a member's Entra id | `204`; the member is the consultant (`chosen`), and their Entra id is recorded on the consultant when the consultant has none and no other consultant holds it. 404 for an unknown chat, 422 for someone not among the chat's members |

- **`TeamsChatList`**: `{chats: [TeamsChatItem], latest_scan: TeamsScanSummary | null, discovery_enabled, watching_enabled}`; the two flags are `TEAMS_DISCOVERY_ENABLED` and `TEAMS_ENABLED`.
- **`TeamsChatItem`**: `{id, title, parsed: {stack, consultant, client, start_date, end_date} | null, quick_add_line, match_status, placement: TeamsPlacement | null, candidates: [TeamsPlacement], watch_state, watched_at, stopped_at, members: [{oid, name}], consultant_member: {oid, name} | null, consultant_member_match, last_message_at, history_state, error_message}`. `parsed` is null when the title could not be read, and `error_message` then says why ("Title not read: …"), or why the members could not be read ("Members not read: …"). `quick_add_line` is the title rewritten as a quick add line when it was read, else the title itself.
- **`TeamsPlacement`**: `{id, consultant_name, client_name, project_name, start_date, expected_end_date, status}`.
- **`TeamsScanSummary`**: `{id, started_at, finished_at, status, chats_seen, chats_added, chats_matched, error_message}`; `status` is `running | completed | failed`.
- **Values**: `match_status` is `matched | chosen | needs_choice | unmatched | unparsed` (`TeamsChatMatch`); `watch_state` `not_watched | watching | stopped | failed` (`TeamsWatchState`); `consultant_member_match` `matched | chosen | needs_choice | unmatched` (`FolderMatchStatus`); `history_state` `none | stored | analysing | analysed` (`HistoryState`).
- **Watching**: with `TEAMS_ENABLED`, a chat tied to an active placement whose expected end has not passed (UK date) is watched, and its members are read to find the consultant; a chat whose placement ended stops being watched and keeps what it had. The review runs after every discovery pass, a register edit of the placement, and the links above.

### Sessions
Reading a session is for anyone whose scope covers its placement (the global roles read all; a PS or SME reads the placements naming them, a CDM the placements of the consultants they manage). Creating, retrying and correcting the kind are for PMO managers and admins.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | `/sessions/upload` | `pmo_manager`, `admin`; 10/min | multipart: `file`, `placement_id`, `held_at` (ISO 8601 with an offset) | `202` `SessionCreated`; the recording is stored and the session's job queued |
| POST | `/sessions/url` | `pmo_manager`, `admin`; 10/min | `{url, placement_id, held_at}` (`held_at` with an offset) | `202` `SessionCreated`; the URL is checked now and downloaded by the job |
| GET | `/sessions?consultant_id=&status=` | any role | — | `SessionListItem[]`: the sessions in the caller's scope, newest call first; both filters optional. Not logged |
| GET | `/sessions/{session_id}` | session scope (logged) | — | `SessionDetail`; writes an `access_log` row (the session's placement, the path); 404 outside scope |
| GET | `/sessions/{session_id}/media-url` | session scope | — | `{url, content_type, expires_in_seconds}`: 15 minutes. On S3 a presigned URL answering with the recording's media type; on local storage a link to `/sessions/{session_id}/media?token=…`. 404 when no recording is stored. Not logged |
| GET | `/sessions/{session_id}/media?token=` | token (no Bearer) | — | The stored recording, with Range support (`206`), on local storage only; 404 on S3, and for a bad, expired or other session's token |
| PATCH | `/sessions/{session_id}/kind` | `pmo_manager`, `admin` (and session scope) | `{kind}`, a `SessionKind` | `SessionDetail`; the kind is marked as set by a person, and a later analysis keeps it. It cannot be cleared |
| POST | `/sessions/{session_id}/retry` | `pmo_manager`, `admin` (and session scope); 10/min | — | `202` `SessionCreated`; a `failed` session goes back to `transcribed` when it has a transcript (analysis only), else to `uploaded` (the copy or download is skipped when the recording is stored), and is queued. 409 for any other status |

- **`SessionListItem`**: `{id, placement_id, consultant: {id, name}, client: {id, name}, project: {id, name}, held_at, duration_seconds, kind, status, error_message, signal_count, action_count}`. `kind` is a `SessionKind` (`onboarding | technical | check_in | escalation | other`) or `null` until classified.
- **An SME** (`sme` role) sees only the Technical signals on the session page, and the list's `signal_count` counts only those for them; the transcript, summary, issues and actions are the same for every reader.
- **`SessionDetail`**: the list item's fields, plus `kind_overridden`, `session_class` (the pipeline's class), `project_phase`, `source`, `original_filename`, `quotes_rejected`, `has_recording`, `summary`, `speakers` (`{label: {role, name}}`), `utterances` (`[{speaker, text, start_ms, end_ms}]`), `signals`, `issues`, `actions`, `closed_actions`, `cost` (`{transcription_usd, analysis_usd, total_usd}`) and `node_errors` (`[{node, error, ...}]` for the global roles, `null` for everyone else).
- **Signal**: `{id, category, dimension, polarity, severity, confidence, quote, note, speaker_role, offset_ms, issue_id}`. **Issue**: the issues this call raised or saw again, as they stand now: `{id, topic, status, occurrence_count, first_seen_at, last_seen_at, resolved_at, offset_ms}` (`offset_ms`: where this call first talks about it). **Action**: `{id, description, owner_role, owner: {id, full_name, email} | null, quote, offset_ms, due_text, due_date, status, closed_at}`; `closed_actions` are earlier actions this call said were done.
- The enumerations are those of `backend/app/models/enums.py`.

- **Upload checks**: an allowed extension (`ALLOWED_EXTENSIONS`), first bytes that match it (422 "The file's content is not WEBM…" otherwise), and at most `MAX_UPLOAD_SIZE_MB` (500). A body over the limit plus 1 MiB is refused with **413** as it arrives, before it is spooled; a file over the limit is refused with 422.
- **URL checks**: `https` only; every address the host resolves to must be public, on every redirect (422 "The URL points to a private or internal address"); a URL needing sign-in answers 502. The recording type and size are checked again as the job downloads it.
- **`held_at`** without an offset is a 422; it is stored in UTC. An unknown placement is a 404.

### Risk board and placement health
The board and the placement (consultant) page read the stored health snapshots and flags; nothing is scored on read. Both routes answer in one of two views, named by `view`:
- **`full`**: PMO managers and admins, a PS for the placements naming them, and a CDM for the placements of the consultants they manage.
- **`technical`**: an SME (by role). The Technical score and its own trend (`technical_trend`, from the Technical score alone) are given; `overall`, `risk_level`, `trend`, `trend_delta`, the other five scores and the snapshot's `signal_count` are `null`, flags are `[]`, evidence is Technical only, and the register omits `extension_status`, `rate_band` and `ended_reason` (`null`).

| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/risk-board` | any role; cut to the caller's scope | `RiskBoardRow[]`, in board order. Not logged |
| GET | `/placements/{placement_id}/health` | placement scope (logged) | `PlacementHealth`; writes an `access_log` row (the placement, the path); 404 outside scope, like a missing placement |

- **Flag order** (board and page): critical first, then the oldest opened, then the PRD's trigger order.
- **Board order** (full view): red, amber, green, then not scored (no snapshot yet, or no signal in the lookback); within a level the trend down, flat, up, then none; then the lower overall; then consultant name. **Technical view**: the lower Technical score first, not scored last, then name, so the order cannot reveal the overall ranking. Only active placements are listed. The PS, CDM, client, stack and risk-level filters are applied by the page.
- **`RiskBoardRow`**: `{placement_id, view, consultant, client, project, ps, cdm, stack, start_date, weeks_in, scored, computed_at, overall, risk_level, trend, trend_delta, technical, technical_trend, technical_trend_delta, open_flags: [{id, trigger, severity, opened_at}], last_call_at, days_since_last_call, next_action: {id, description, owner_role, due_date} | null}`. `consultant`, `client` and `project` are `{id, name}`; `ps` and `cdm` (the consultant's CDM) are `{id, full_name, email} | null`; `stack` is the placement's, for the board's stack filter. `weeks_in` is whole weeks since the start (0 before it); `last_call_at` is the latest completed call and `days_since_last_call` the UK days since it. `next_action` is the open or overdue action with the earliest due date, past dates included; actions without a due date are never shown there.
- **`PlacementHealth`**: `{placement_id, view, consultant, client, project, weeks_in, register_fields, latest, history, open_flags, sessions, open_issues, actions, other_placements, thresholds}`.
  - **`register_fields`**: `{start_date, expected_end_date, status, stack, client_manager_name, ps, sme, cdm, extension_status, rate_band, ended_reason}`.
  - **`latest`** (`null` before the first recompute): `{computed_at, reason, scored, scores: {delivery, technical, relationship, engagement, onboarding, communication}, overall, risk_level, trend, trend_delta, technical_trend, technical_trend_delta, signal_count, weights_version, evidence: [{dimension, signal_count, contributors: [{signal, weight, value}]}]}`; the contributors are the signals that pulled each dimension furthest from the prior, as the recompute stored them.
  - **`history`**: every snapshot, oldest first: `{computed_at, reason, scored, scores, overall, risk_level, trend, technical_trend}`.
  - **`open_flags`**: `[{id, trigger, severity, opened_at, evidence: [signal]}]`, evidence newest first.
  - **Evidence `signal`**: `{id, source_kind, source_id, dimension, polarity, severity, confidence, quote, note, speaker_role, occurred_at, offset_ms, indicator}`; `source_id` is the session (or message) it was said in, `offset_ms` where in the recording.
  - **`sessions`**: the placement's calls, newest first: `{id, held_at, kind, status, duration_seconds, signal_count, action_count}` (Technical signals only in the technical view); a completed one is a marker on the chart.
  - **`open_issues`**: `[{id, topic, status, occurrence_count, first_seen_at, last_seen_at}]`, longest open first.
  - **`actions`**: every action of the placement, open and overdue first by due date (undated last), then done ones, newest closed first: the session page's action fields plus `source_kind` and `source_id`.
  - **`other_placements`**: the consultant's other placements in the reader's scope, newest start first: `{id, client, project, start_date, expected_end_date, status}`.
  - **`thresholds`**: `{green_from, amber_from}`, the RAG thresholds of the health configuration in use (`HEALTH_CONFIG_VERSION`; 7.0 and 5.0 in v1), given in every view. The page's chart bands and dimension colours come from them, never from constants of its own.
- The enumerations (`RiskLevel`, `Trend`, `RiskTrigger`, `FlagSeverity`, `SnapshotReason`, `HealthView`) are those of `backend/app/models/enums.py`.

## Common Response Formats
### Error Response
```json
{
  "detail": "Error message"
}
```
A rate-limited request answers `429`.
