# Sprint 4: Teams Chat

**Status**: `in-progress` (plan approved 2026-10-14)
**Duration**: 2026-10-14 – 2026-12-01 (re-planned 2026-11-17 from 2026-10-27; no work 2026-10-19 – 2026-11-16)
**Objective**: PRD Phase 3 (ROADMAP Milestone 3): read the PMO group chats (titled `PRJ ITC …`) through Microsoft Graph, store their messages, run the chat pipeline into the one `signals` table, track cadence, add the gone-quiet and missed-commitment triggers, and show messages on the placement page.
**Exit gate (PRD)**: one real group watched for a week; new posts appear within 5 minutes; no message read outside the watched groups.
**Branch**: `develop`
**Previous sprint**: Sprint 3 (Visual Redesign), complete 2026-10-13; see `docs/handover/sprint-03-handover.md`. Its plan, Decisions Log and session notes are in git history (`b4efa3a`).

---

## Research Findings Summary
Microsoft Graph pages read 2026-10-14; Graph rules change, so re-check before acting.

- **Polling rule** ([Teams API overview, "Polling requirements"](https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview)): "If your app polls to see whether a resource has changed, you can only do that once per day." Anything faster must use change notifications (webhooks); apps that break the rule risk extra throttling or suspension. So the PRD's poll every 2 to 5 minutes is replaced by a webhook with a once-a-day catch-up read (user decision below). GETs that are not polling (a notification's message, a backfill) are allowed.
- **Change notifications for chat messages** ([chatMessage notifications](https://learn.microsoft.com/en-us/graph/teams-changenotifications-chatmessage)):
  - `/appCatalogs/teamsApps/{teams-app-id}/installedToChats/getAllMessages`: every chat where our Teams app is installed, in one subscription; application permission `Chat.Read.WhereInstalled` (not yet requested or granted).
  - `/chats/{id}/messages`: per chat; RSC `ChatMessage.Read.Chat` is supported there "for the beta version only currently", or `Chat.Read.All` on v1.0.
  - Without resource data no encryption certificate is needed: the notification carries the message's resource path, and the message is then read with a GET.
- **Subscription lifetime** ([subscription resource](https://learn.microsoft.com/en-us/graph/api/resources/subscription)): chatMessage at most 4,320 minutes (three days); beyond one hour a `lifecycleNotificationUrl` is required (`subscriptionRemoved`, `reauthorizationRequired`, `missed`). chatMessage latency: under 10 s on average, at most 1 minute. The endpoint must answer the validation request (a `validationToken` query parameter, echoed as text/plain) within 10 seconds; `clientState` (up to 128 characters) lets the endpoint check a notification came from the subscription.
- **Reading messages** ([list chat messages](https://learn.microsoft.com/en-us/graph/api/chat-list-messages)): least-privileged application permission is RSC `ChatMessage.Read.Chat`; `$top` at most 50; `$orderby` `lastModifiedDateTime` or `createdDateTime`, descending only; `$filter` on `lastModifiedDateTime` (`gt`, `lt`) only with `$orderby` on the same property; pages through `@odata.nextLink`. System events come as `messageType` `systemEventMessage`; deleted messages carry `deletedDateTime`; bodies are often HTML.
- **Adding the app to a chat** ([add app to chat](https://learn.microsoft.com/en-us/graph/api/chat-post-installedapps)): `POST /chats/{id}/installedApps` with `teamsApp@odata.bind` to `appCatalogs/teamsApps/{catalog id}` and `consentedPermissionSet.resourceSpecificPermissions` matching the manifest (`ChatMessage.Read.Chat`, `ChatMember.Read.Chat`, both Application); `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All` (granted) can install an app that needs RSC, the plainer `…ReadWriteSelfForChat.All` cannot. 201 on success.
- **Catalog id** ([list teamsApp](https://learn.microsoft.com/en-us/graph/api/appcatalogs-list-teamsapps)): an org-published app's catalog `id` is generated and differs from the manifest id (`0f2eaf35-…`, stamped as `externalId`). Looking it up app-only needs `AppCatalog.Read.All` (not granted); a one-off lookup by a signed-in user (Graph Explorer, `AppCatalog.Submit` delegated) and a setting avoid the extra permission.
- **Throttling** ([Teams service limits](https://learn.microsoft.com/en-us/graph/throttling-limits)): per app per tenant, `GET /chats/{id}/messages` 20 rps and 1 rps per chat; `GET /users/{id}/chats` 20 rps (1 rps per user); `POST installedApps` 30 rps and 1 rps per chat. A sustained rate of about 83% of the listed value is also enforced, so a backfill paces itself and honours `Retry-After` with exponential backoff.
- **Open to test on the tenant** (no page answers them): whether an install through Graph works while the Teams app shows "This app is not available. Please check with your admin"; whether a package with RSC permissions only (no tab or bot) installs into a chat this way.
- **Credentials**: msal Python reads a `.pfx` directly (`client_credential={"private_key_pfx_path": ..., "passphrase": ...}`, since 1.29/1.30); `scripts/teams/verify_chat_access.py` already uses it. msal is not a backend dependency yet. The certificate is only on the developer's machine; secrets reach the backend container only as environment variables from `pmo-intelligence/staging/app` (`infra/modules/environment/secrets.tf`, `ecs.tf`).

### Codebase survey (2026-10-14)
- **Ready**: `SourceKind.MESSAGE`; `CHAT_PRIORITY = 0` in `processing_queue.py`; `RiskTrigger.GONE_QUIET` and `MISSED_COMMITMENT` with meanings and severities (medium); `SpeakerRole` documented for chat authors; `processing_costs.message_id` (no FK yet); `consultants.entra_oid` ("links a Teams message author to the consultant"); migration 005 already allows `message` source kinds and the `overdue` action status; the frontend has the trigger labels and `SOURCE_KINDS`.
- **Missing**: `teams_groups` and `messages` models (next migration 010); Graph settings; any HTTP retry code (a Graph client needs its own 429/503 handling); a message class enumeration; trigger inputs for cadence and actions; quiet and missed-commitment thresholds in the health configuration (its model forbids unknown keys, so a new `v2.json`); a snapshot reason for chat; nothing sets an action `overdue`.
- **Session pipeline reuse** (`app/ai/session/`): `llm_node` (timeout, cost, non-fatal) is typed to the session state and prefixes `session_`; `TranscriptIndex` in `quote_check.py` already accepts any list of `{text, speaker, start_ms}`, so a chat thread can be checked the same way; the prompts' `common.py` text assumes a call. Tests mock the model with `FakeModel` (`tests/unit/session_pipeline_helpers.py`).
- **Title parsing**: the quick add's `parse_line` (`register_quick_add.py`) needs spaces round every separator, five parts, `D/M/YYYY` or `D-M-YY`, and a full consultant name; it fails on the 109 titles. `recordings/folder_names.py` (`fold`) and `recordings/name_match.py` (`match_folder`, first or last name as a whole word) already handle first-name-only titles.
- **Loops**: `recordings/periodic.py` and `health_jobs.py` show the loop, fixed-id job, runner registration and takeover patterns to copy.
- **Frontend**: the placement page's left column ends with "Calls" (a messages section fits after it); `EvidenceItem` links only session evidence; the risk board's "Last call" column is the pattern for "Last post"; Admin tabs are listed in `ADMIN_TABS` (`AdminView.tsx`) and `RecordingsTab` with `useRecordings` is the pattern for a Teams tab.

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|
| Live route (2026-10-14) | **One app-wide webhook**: a change-notification subscription to `/appCatalogs/teamsApps/{id}/installedToChats/getAllMessages` (needs application permission `Chat.Read.WhereInstalled` with admin consent), renewed before its three-day limit, plus a once-a-day catch-up read per chat with a date range; messages read with RSC `ChatMessage.Read.Chat` | Per-chat webhooks with `Chat.Read.All`; per-chat webhooks with RSC on beta; poll every 5 minutes as the PRD says (breaks Microsoft's rule) |
| Which chats (2026-10-14) | **Every `PRJ ITC` chat linked to an active placement whose end date has not passed** is watched automatically (the app added to it); old engagements are never touched | Pilot chats a PMO manager turns on; all 151 |
| Title matching (2026-10-14) | **Tolerant parser plus an Admin link**: the parser widened for the variants seen (no spaces round dashes, dates in brackets, D/M/YY, YYYY-MM-DD, `PRJ ITC-`); a title matching exactly one placement links automatically; the rest are listed in Admin > Teams to link to a placement, or to create its placement from the title (prefilled, as the quick add does) | Auto-create placements like the quick add; manual link only |
| History (2026-10-14) | **Whole chat history** read when a chat is first watched | 30 days; since 2026-07-24; from now on only |
| Analysis of history (2026-10-14) | **Store and analyse everything** through the chat pipeline (older signals never move a score, but are kept as evidence and for the later "who else had this blocker" search) | Store all, analyse only the 104 days the health model reads |
| Consultant in the chat (2026-10-14) | **Name match with an Admin override**: the chat's members (RSC `ChatMember.Read.Chat`) matched to the placement's consultant by first and last name, as recording folders are; a single match sets `consultants.entra_oid`; none or several, Admin asks a person to pick | A person picks for every chat; match by email |
| Working days (gone quiet, 2026-10-14) | **Monday to Friday minus England and Wales bank holidays**, the holidays and the 5 days in the health configuration (a new version, v2) | Monday to Friday only; 7 calendar days |
| Missed commitment (2026-10-14) | **Overdue plus no consultant update**: an open action past its due date becomes `overdue` (any owner); a consultant-owned overdue action opens the flag only if the consultant has neither posted in the chat nor had a completed call since the due date; the chat pipeline may close actions from messages, as calls do | Any consultant action past due opens the flag; past due by N working days |
| Dates (2026-10-14) | **2026-10-14 – 2026-10-27** (two weeks) | Three weeks; one week |
| Re-plan (2026-11-17) | **End 2026-12-01**, phases dated from the exit gate's week: Phase 5 17–20 Nov (on staging by Fri 20 Nov, the week starting then), Phase 6 23–25 Nov, Phase 7 26 Nov, Phase 8 27 Nov, Phase 9 30 Nov – 1 Dec (the week ends 27 Nov). Scope unchanged | Carry on without dates; close Sprint 4 at Phase 5 and move Phases 6–9 to Sprint 5 |
| Backlog pulled in (2026-10-14) | **All four**: the risk board's project in its own column; the `sessions.spec.ts` seed (a decodable WebM, the cold-start allowance on the retry test); remove the unused `.chart-animate` CSS; mypy strict on the backend tests, with `make lint` and CI widened to `app tests` | Any subset |
| Graph certificate (2026-10-14) | **In the app secret**: two new keys in `pmo-intelligence/staging/app` (`GRAPH_CERTIFICATE_PFX_BASE64`, `GRAPH_CERTIFICATE_PASSWORD`), injected as environment variables; Terraform adds the key names, the values are put with `put-secret-value` | A separate secret |
| Start (2026-10-14) | **A spike on the tenant first**: a script installs the app into one test chat titled `PRJ ITC TEST …`, reads it with RSC, and creates and validates one `installedToChats` subscription; the build phases start only once it works; if it fails, stop and decide | Build and test as we go |

| Pipeline unit (2026-10-14) | **One job per chat, batched**: a notification queues the chat's job (the queue merges repeats); the job takes every unanalysed message in the chat, with the messages before them as context, classifies them in one call, drops noise, and extracts from the rest | One run per message |
| Catalog id (2026-10-14) | **A one-off lookup kept as a setting**: a signed-in person runs `appCatalogs/teamsApps?$filter=externalId eq '0f2eaf35-928a-4321-9261-692893f270ff'` in Graph Explorer during the spike; the id goes into `TEAMS_CATALOG_APP_ID`. No new permission | Request `AppCatalog.Read.All` |
| Cost guard (2026-10-14) | **Count first, a person confirms**: watching a chat stores its whole history at once; analysing stored history waits until Admin > Teams shows the message count and an estimated LLM cost and a PMO manager presses "Analyse history". New messages are analysed as they arrive | A monthly cap; no guard |
| Placement ends (2026-10-14) | **Remove the app, keep the data**: the app removes itself from the chat (the chat shows it), so nothing more is read; stored messages and signals stay (retention is product Phase 5); an extension adds it back. **Changed 2026-10-16** (route below): the chat's subscription is deleted and nothing more is read; the data stays | Stop processing but stay installed; keep watching until turned off |
| **Route after the spike (2026-10-16)** | **`Chat.Read.All` for good**: the install through Graph was refused (`AppScopeIsNotAllowed`: an RSC-only Teams app cannot be added to a group chat). Watched chats are read with the tenant-wide application permission `Chat.Read.All` (granted 2026-10-14), with **one change-notification subscription per watched chat** (`/chats/{id}/messages`, v1.0) and no app install; members read with `Chat.ReadBasic.All`. Our code calls Graph only for `PRJ ITC` chats linked to an active placement. **Replaces** the app-wide `installedToChats` subscription (the "Live route" row), the install and removal in Phase 4, and RSC reads; chats no longer show that anything was added, so HR's notice must say the group is read | A Teams app 1.0.1 with a group-chat tab, with `Chat.Read.All` as a bridge until approved; the same package, waiting for approval |
| Phase 3 names after the route change (2026-10-18) | **Watch state** `not_watched`, `watching`, `stopped` (placement ended: subscription deleted, data kept), `failed`, with `watched_at` and `stopped_at`; the **consultant member's match** reuses `FolderMatchStatus`; **`messages.message_type`** is Graph's `messageType` as given (no CHECK, only `message` analysed); **`TEAMS_CATALOG_APP_ID` dropped** (the id stays in `TEAMS-GRAPH-SETUP.md`, Part D) | Keep the plan's install names; a `subscribing` state; a new member-match enum or `TeamsChatMatch`; an enum with a CHECK; keep the catalog id setting |
| Phase 4 watching and discovery (2026-10-18) | **Watching selected in Phase 4, subscribed in Phase 5**: the `teams_watch` job marks an eligible chat `watching` (`watched_at`), reads its members and matches the consultant member, and marks a chat whose placement ended `stopped`; Phase 5's manager creates the subscription of every `watching` chat without one; no message is read in Phase 4. **Discovery has its own switch**, `TEAMS_DISCOVERY_ENABLED` (Terraform `teams_discovery_enabled`), on for staging at the end of Phase 4: chat titles and title matching only (`Chat.ReadBasic.All`); the watch job and members stay behind `TEAMS_ENABLED` | Eligibility shown only, the watch job in Phase 5; one switch for everything |
| Discovery accounts (2026-10-18) | `Sunny.Dhanoe@InformationTechConsultants.com` and `uttam.kumar@InformationTechConsultants.com`, read from the directory and confirmed by the user; Sunny's `.co.uk` guest account not used | — |
| Discovery history (2026-10-18) | **Migration 011, `teams_scans`**, like `recording_scans`: `started_at`, `finished_at`, `status` (`ScanStatus`), `chats_seen`, `chats_added`, `chats_matched`, `error_message`; a pass cut short by a restart failed by the takeover sweep | A `source` column on `recording_scans`; a log line only |
| Admin > Teams layout (2026-10-18) | **A card of the chats waiting for a person, then a table of every chat**, as the Recordings tab does: the card lists unparsed, unmatched and several-placement chats and unclear consultant members, each with its fix; the table has match and watch filters and a search | One table with filters; two pill sub-tabs |

## Task Checklist

>>> CURRENT PHASE: Phase 5 (Phase 4 rolled out and checked on staging 2026-11-17)

Every phase: re-read this plan, code and tests, the doc list walked item by item, the commit checkpoint, then stop. Backend: `make test-backend` with `-rf`; frontend Vitest with `--maxWorkers=4`; e2e with one worker after `docker compose up --build -d --wait <changed service>`. Every Graph call in tests is mocked (an `httpx` mock transport); no test calls Microsoft. Test data uses made-up names only: real chat titles name real consultants, so the title shapes are reproduced with invented names. Every push: both CI filters read before saying what it runs and deploys, and the deploy recorded in DEPLOYMENT's status in the next commit.

### Phase 0: Plan
**Code work**
- [x] Plan approved (2026-10-14, with its judgement calls)

**Doc updates (concurrent)**
- [x] This file; `ROADMAP.md` (Milestone 3 dated Sprint 4, the webhook replacing the poll noted); `BACKLOG.md` (the four pulled items marked for Sprint 4; open question 4 notes the webhook and `Chat.Read.WhereInstalled`)

**Commit checkpoint**
- [x] `docs: plan sprint 4` (a53aba4, 2026-10-14; pushed)

### Phase 1: Spike on the tenant (scripts only, nothing deployed)
**Setup (the user and the tenant admin)**
- [x] (added by the user and admin-consented 2026-10-16; unused after the route change) `Chat.Read.WhereInstalled` (app role `1c1b4c8e-3cc7-4c58-8470-9b92c9d5848b`, read from the tenant 2026-10-14) added to the Graph app registration (`az ad app permission add`, by the user) and admin consent requested (the request text added to `TEAMS-GRAPH-SETUP.md`)
- [x] The catalog id looked up in Graph Explorer by a signed-in person and recorded: **`74c9afc8-4084-4653-876f-2d63f325ada7`** (2026-10-16, by the user; `distributionMethod` organization, `externalId` the manifest id; the Azure CLI's token could not: it lacks `AppCatalog.Submit`/`AppCatalog.Read.All`, tried 2026-10-14)
- [x] (created by the user 2026-10-16, three PMO staff) A test group chat titled `PRJ ITC TEST - <made-up name> - <made-up client> - 1/10/2026 - 31/3/2027` with the user and one colleague

**Code work**
- [x] (written 2026-10-14, run against the tenant 2026-10-16; `subscribe --chat-id` added after the route change) `scripts/teams/spike_chat_route.py` (run with `uv run --with msal --with requests`, certificate as in `verify_chat_access.py`): (1) add the app to the test chat (`POST /chats/{id}/installedApps` with the RSC permission set); (2) list its members (`ChatMember.Read.Chat`); (3) read its messages (`ChatMessage.Read.Chat`), printing ids, times, types and author ids only, never content; (4) create one subscription to `installedToChats/getAllMessages` without resource data, pointing at a local receiver; (5) remove the app again (`DELETE installedApps`), confirming the "placement ends" path
- [x] (written and checked locally 2026-10-14: validation echo, 202, client state check) `scripts/teams/spike_receiver.py`: a local HTTP receiver that answers the validation token and logs each notification's subscription id, change type and resource path only, reached through a temporary tunnel (Microsoft dev tunnels) for the length of the spike
- [x] (run 2026-10-16; see "Spike results so far" and `TEAMS-GRAPH-SETUP.md` Part D: install refused, `AppScopeIsNotAllowed`; route changed to `Chat.Read.All` by the user; a per-chat subscription notified a post within about a second, and its edit and deletion) Results: install works (or the exact error) while the app shows "not available"; an RSC-only package installs; a test post's notification arrives and how fast. **If the install or the subscription fails, stop and decide with the user before Phase 3**

**Doc updates (concurrent)**
- [x] (also `BACKLOG.md`: the RSC items superseded, two follow-ups; `ROADMAP.md` and `ARCHITECTURE.md` "Teams Connector" and `> Status:`: the route) `docs/integrations/TEAMS-GRAPH-SETUP.md` (a "Part D: spike" with steps and results; the results table: catalog id, `Chat.Read.WhereInstalled`, install and notification results), `FEATURES.md` (the spike scripts as operator tools), `CHANGELOG.md` (README: no new make target)

**Commit checkpoint**
- [x] `chore: add the chat route spike scripts` (62b2a0a, 2026-10-16; pushed)

### Phase 2: Backlog clean-ups (independent; can run while the admin consent is awaited)
**Code work**
- [x] (2026-10-16) Risk board: `client` and `project` as separate columns in `RiskBoard.tsx`; the search and the client filter unchanged
- [x] (2026-10-16; user choice: recorded with Chromium's MediaRecorder, committed as `app/cli/e2e_recording.webm`, 1,179 bytes, 0.90 s of silence in Opus; the e2e test now also waits for the player's metadata) `sessions.spec.ts` seed: a small decodable WebM in `app/cli/seed_e2e_session.py`, and the cold-start allowance (`test.setTimeout(90_000)`) on the retry test
- [x] (2026-10-16; the `fade-slide-in` keyframes too, which only it used) Remove `.chart-animate` and its delay classes from `globals.css` (and its reduced-motion block), after `git grep` shows no user
- [x] (2026-10-16; 70 errors in 17 files once a module-name clash, `unit.x` vs `tests.unit.x`, was cleared with `explicit_package_bases` in `pyproject.toml`; `testcontainers` added to the untyped modules) mypy strict on `tests`: fix the 57 errors in 8 test files; `make lint` and the CI mypy step widened to `app tests`
- [x] (2026-10-16: backend 1046 passed, 764 unit + 282 integration; frontend 266; e2e 23 of 23 with one worker, `sessions.spec.ts` 3 of 3 runs alone with the default workers; `make lint` clean) Tests: `RiskBoard.test.tsx` (the two columns); e2e 23 of 23 with one worker, then `sessions.spec.ts` three times alone; `uv run mypy app tests` clean

**Doc updates (concurrent)**
- [x] (2026-10-16 with the two commits; DEPLOYMENT's status after the push, 2026-10-18) `ARCHITECTURE.md` (Risk board row; CI table's mypy step; `> Status:`), `DESIGN.md` (risk board columns; the chart entrance removed), `BACKLOG.md` (the four items ticked), `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`, `DEPLOYMENT.md` status for the push (README: `make lint` row if its description changes)

**Commit checkpoint**
- [x] (1c250a0 and the feat commit, 2026-10-17; the shared docs split by hunk) `test: type-check the backend tests` and `feat: show the risk board's project in its own column` (two commits; the seed and CSS fixes with the second, or as `fix:`/`chore:` if the user prefers)

### Phase 3: Data model, settings and the Graph client
**Code work**
- [x] (2026-10-18; `MESSAGE_CLASS_MEANINGS` too, and the frontend's `SNAPSHOT_REASONS` mirror) `app/models/enums.py`: `MessageClass` (the PRD's classes: consultant update, question, stakeholder context, praise, concern, escalation, administrative, noise, with meanings for the prompts), `TeamsChatMatch` (`matched`, `chosen`, `needs_choice`, `unmatched`, `unparsed`), `TeamsWatchState` (`not_watched`, `watching`, `stopped`, `failed`; changed 2026-10-18, no install), the consultant member's match status reusing `FolderMatchStatus`, `HistoryState` (`none`, `stored`, `analysing`, `analysed`), `SnapshotReason.CHAT`
- [x] (2026-10-18: `app/models/teams.py`, `alembic/versions/010_create_teams_chat_tables.py`; `teams_groups.members` added for the member picker; the downgrade deletes `chat` snapshots; migration tests 11 of 11 with `alembic check`) Migration 010: `teams_groups` (`graph_chat_id` unique, `title`, the parsed title fields, `placement_id`, match status and candidates, `consultant_member_oid` and its match status, watch state, `watched_at`, `stopped_at`, `sync_requested_at`, `last_synced_at`, `last_message_at`, history state, `error_message`), `messages` (`teams_group_id`, `graph_message_id` unique with the group, `author_entra_oid`, `author_name`, `author_role`, `posted_at`, `last_modified_at`, `deleted_at`, `body_text`, `reply_to_message_id`, `message_type` (Graph's value as given, no CHECK), `message_class`, `is_noise`, `is_history`, `analysed_at`), `graph_subscriptions` (`subscription_id`, `teams_group_id`, `resource`, `expires_at`; one per watched chat since 2026-10-16), the FK `processing_costs.message_id` → `messages`, and the snapshot reason's CHECK; the PRD's `kind`/`graph_team_id`/`delta_token` columns not built (group chats only, no delta for chats)
- [x] (2026-10-18; also `GRAPH_TIMEOUT_SECONDS` 30 and `GRAPH_MAX_RETRIES` 5) `app/config.py`: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CERTIFICATE_PFX_BASE64`, `GRAPH_CERTIFICATE_PASSWORD`, `GRAPH_CLIENT_STATE` (the webhook secret), `TEAMS_DISCOVERY_ACCOUNTS` (UPNs; `TEAMS_CATALOG_APP_ID` dropped 2026-10-18, no install), `TEAMS_ENABLED` (off by default), `TEAMS_NOTIFICATION_BASE_URL`; `.env.example`
- [x] (2026-10-18: the .pfx read with `cryptography` into msal's PEM credential; requests naming one chat or user spaced 1.25 s; `GraphError` in `app/utils/exceptions.py`; `msal` 1.39.0 added, untyped) `app/services/teams/graph_client.py`: msal certificate token (cached until expiry), one `httpx.AsyncClient` with a finite timeout and an injectable transport, paging through `@odata.nextLink`, `Retry-After` and exponential backoff on 429, 503 and 504, pacing under the per-chat 1 rps; any failure a `GraphError`. `uv add msal` (mypy override if untyped)
- [x] (2026-10-18: `secrets.tf`, `ecs.tf`, `variables.tf`, staging `main.tf`; `random_password.graph_client_state` as a new environment's placeholder; the three keys put into the secret first, on the user's say-so, since a task whose secret lacks a named key does not start; applied 10:42 UTC, 2 added, 1 changed, 1 destroyed, revision 4 to 5, ownership after 110 s) Infra: `app_secret_keys` gains the Graph secrets and `GRAPH_CLIENT_STATE`; the non-secret ids in the backend environment; `teams_enabled` module variable (false until Phase 5's rollout). Terraform plan shown, applied only with approval (replaces the backend task definition, so the backend redeploys); the values put with `put-secret-value` by the user
- [x] (2026-10-18: `test_migrations.py` 11, `test_graph_client.py` 23, `test_config.py` 7; backend 1072 passed, frontend 266, e2e 23 of 23 with one worker; `make lint` clean) Tests: migration up and down; the Graph client (token reuse, paging, `Retry-After`, backoff limit, error mapping) on a mock transport; settings

**Doc updates (concurrent)**
- [x] (2026-10-18; README unchanged: no new make target or doc) `ARCHITECTURE.md` (Data Model: migration 010 with differences from the draft; Backend rows for Settings, Enumerations, the Graph client; Infrastructure; `> Status:`), `DEPLOYMENT.md` (a new section "12. Teams chat (Graph secrets, catalog id)"; status), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [x] (06ee758, 2026-10-18; pushed, CI run 39119613355 green, both sides deployed) `feat: add the teams chat data model and graph client`

### Phase 4: Discovery, title matching, watching and Admin > Teams
**Code work**
- [x] (2026-10-18; also D-M-YYYY; an end before the start leaves the chat unparsed) `app/services/teams/chat_titles.py`: the tolerant parser (hyphen or en dash with or without spaces, `PRJ ITC-` and `PRJ ITC - <stack> -`, dates `D/M/YYYY`, `D/M/YY`, `D-M-YY`, `YYYY-MM-DD`, in brackets or not, a missing or extra part reported); the quick add's `parse_line` left as it is
- [x] (2026-10-18; the consultant matched only among the placements with the title's client and start date) Matching (`chat_match.py`): client by normalised name, consultant with `name_match.match_folder` (first or last name), placement by consultant, client and start date (any of the client's projects); exactly one is `matched`, else `needs_choice` or `unmatched`; `matched` and `chosen` never changed by a later scan
- [x] (2026-10-18: job, daily loop behind `TEAMS_DISCOVERY_ENABLED`, `teams_scans` (migration 011) and its takeover sweep, "Scan now" (409 while discovery is off); the members are read by the watch job, not here) Discovery job (`teams_discovery`, fixed id, backlog priority): lists `TEAMS_DISCOVERY_ACCOUNTS`' chats (`Chat.ReadBasic.All`), keeps `PRJ ITC` titles, merges by chat id, upserts `teams_groups`, re-matches the undecided ones; once a day (the loop pattern of `recordings/periodic.py`) and on "Scan now"
- [x] (2026-10-18: `teams/watch.py`; also `teams_watch_placement` per placement after a register edit; the review only with `TEAMS_ENABLED`; a failed member read leaves the chat `failed`; a consultant's Entra id recorded only when none and no other consultant holds it; the subscription itself is Phase 5's) Watch policy (`teams_watch` job per chat; changed 2026-10-16, no install): a chat linked to an active placement whose end date has not passed is watched: its subscription created (Phase 5's manager), its members read (`Chat.ReadBasic.All`) and the consultant matched by name (a single match sets `consultants.entra_oid`; otherwise Admin asks); a watched chat whose placement ended or whose end date passed has its subscription deleted and keeps its data; re-evaluated after discovery, a register edit and the daily run
- [x] (2026-10-18; the create-from-title answers the quick add's result, always 200; `QuickAdd.placement_of_line` records each line's placement; the consultant member must be among the chat's members) Routes (`app/api/v1/teams.py`, `pmo_manager` and `admin`; `{chat_id}` routes under `require_roles`, the coverage test extended like `{folder_id}`): `GET /teams/chats` (with the last scan), `POST /teams/scan`, `PUT /teams/chats/{chat_id}/placement`, `POST /teams/chats/{chat_id}/placement` (create from the title through the quick add's writer, the line prefilled and editable), `PUT /teams/chats/{chat_id}/consultant-member`
- [x] (2026-10-18; the layout chosen by the user: a card of the chats waiting for a person, then the table; `DialogShell` exported from the Recordings dialogs and shared; `seed_e2e_teams` for the e2e) Admin > Teams tab (`components/admin/teams/TeamsTab.tsx`, `hooks/useTeamsChats.ts`): the last scan and Scan now; every `PRJ ITC` chat with its title, match, placement, watch state, consultant member, last message and history state; pickers for the placement and the consultant member; "Create placement from title"; polls like the Recordings tab
- [x] (2026-10-18: backend 1188 passed, 865 unit and 323 integration; frontend 277; e2e 24 of 24 with one worker, `admin-teams.spec.ts` new; `make lint` clean) Tests: the parser on every title shape seen (made-up names); matching; discovery and watch jobs on a mock transport (install, remove, member match, failure recorded); every route called and its response read; `TeamsTab.test.tsx`; an Admin e2e (the tab lists seeded chats; links one)

**Doc updates (concurrent)**
- [x] (2026-10-18; also `DEPLOYMENT.md` section 12, the discovery switch; README unchanged: no make target or doc added) `docs/API.md` (Teams section), `ARCHITECTURE.md` (Backend and Frontend rows; a "Teams chat (as built)" section; `> Status:`), `DESIGN.md` (the Teams tab), `TEAMS-GRAPH-SETUP.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [x] (82c036d, eb4a4f4, f37584e, 2026-10-18; pushed and on staging, the discovery Terraform applied (revision 6); daily passes checked 2026-11-17) `feat: find, match and watch the pmo group chats`

### Phase 5: Messages in: history, webhook, subscription and catch-up (17–20 Nov)
**Code work**
- [x] (2026-11-17: `messages.py` `TeamsSync`, the first sync of a watched chat; `message_text.py` for HTML; the author role from the chat (consultant member, PS, SME, CDM, PMO managers by Entra id, else other)) History: when a chat becomes watched, its whole history is read once (`GET /chats/{id}/messages` with `Chat.Read.All`, paced) and stored (HTML to plain text; system events stored as such and never analysed; deletions kept as `deleted_at` with the text cleared), marked `is_history`; the chat's history state becomes `stored`
- [x] (2026-11-17: `api/v1/teams_notifications.py`, `notifications.py`, `require_graph_client_state` in `dependencies.py` (also checks `tenantId`; a request with none kept 403); the chat found by its subscription id; own rate limit 600/min) Webhook (`POST /teams/notifications` and `POST /teams/lifecycle`, public, guarded by `require_graph_client_state`, listed as token-scoped in the coverage test): answers the validation token as text/plain; checks `clientState` in constant time; for each notification records `sync_requested_at` on its chat and queues the chat's sync job (`CHAT_PRIORITY`); answers 202 at once; a notification for a chat not watched is dropped and logged
- [x] (2026-11-17: 5 minutes of overlap below the newest stored change; `last_synced_at` is when the last sync started; an edit clears the pipeline's class; queueing the analysis is Phase 6's) Sync job (`teams_sync`, one per chat): reads messages changed since the chat's watermark (`lastModifiedDateTime gt`), stores new, edited and deleted ones, queues the chat's analysis; a sync is triggered only by a notification, the daily catch-up or a lifecycle `missed`, never on a timer, so the polling rule holds
- [x] (2026-11-17: `subscriptions.py`, job `teams_subscription` per chat after every watch review, on lifecycle events and every 6 h (`PeriodicTeamsUpkeep`, `TEAMS_SUBSCRIPTION_CHECK_SECONDS`); 4,230-minute lifetime; a 404 on renewal makes it again; the catch-up at start and then daily) Subscription manager (changed 2026-10-16: one per watched chat): creates each watched chat's `/chats/{id}/messages` subscription when absent (with a `lifecycleNotificationUrl`), renews each a day before its three-day expiry, re-authorises on `reauthorizationRequired`, recreates on `subscriptionRemoved`, deletes it when the chat stops being watched, and on `missed` queues that chat's sync; a daily catch-up sync of every watched chat (one date-ranged read each)
- [x] (2026-11-17: `teams syncs` re-queue, also chats whose history is unread) Takeover step: chats whose `sync_requested_at` is newer than `last_synced_at` are queued again (a notification taken by the non-owner task during a deploy is not lost); counts logged, zero included
- [ ] Rollout to staging: `teams_enabled` true (Terraform, with approval); the subscription created; the test chat checked (a post appears in the database within 5 minutes)
- [x] (2026-11-17: `test_teams_messages.py` 13, `test_teams_jobs.py` 13 (was 5), `test_teams_sync.py` 10, `test_teams_subscriptions.py` 11, `test_teams_notifications_api.py` 13, coverage 66; backend 1249 passed (892 unit, 357 integration); `make lint` clean) Tests: validation echo, client state refused, notification to job, sync (new, edited, deleted, system event), history paging, subscription create, renew and lifecycle events, takeover requeue

**Doc updates (concurrent)**
- [x] (2026-11-17; also the System Design and Teams Connector lines that still said "poll every 2–5 min") `docs/API.md` (the notification routes), `ARCHITECTURE.md` (Teams chat section; Infrastructure; `> Status:`), `DEPLOYMENT.md` (section 12: turning it on, checking the subscription; status), `TEAMS-GRAPH-SETUP.md` ("Engineering notes" updated: webhook, not polling), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: receive teams chat messages through change notifications`

### Phase 6: Chat pipeline (23–25 Nov)
**Code work**
- [ ] `app/ai/node.py`: `llm_node` generalised (state type and operation prefix as parameters; the session pipeline unchanged in behaviour)
- [ ] `app/ai/chat/` (LangGraph, gpt-5.4-mini, structured output, every node non-fatal, timed, costed, with `CHAT_NODE_TIMEOUT_SECONDS`): `classify` (each new message's `MessageClass`; noise stops there), then in parallel `signals` (dimension, polarity, severity, confidence, quote, note, indicator per `SIGNAL_INDICATORS_BY_CATEGORY`) and `actions` (owner role, due date worked out from the post's UK date, earlier open actions it closes), then `emit` (every quote must be found in the one message it cites, through `TranscriptIndex`; the author's role from the chat's mapping, not the model). Prompts cite the enumerations from `enums.py`
- [ ] Context: the batch's messages plus the previous messages in the chat as context only (never quoted from), the placement's people, the open issues and actions
- [ ] Storing (`chat_analysis.py`): signals with `source_kind` `message`, `source_id` the message, `occurred_at` its post time, no offset; actions and closed actions; a `processing_costs` row per call with `message_id`; `analysed_at` on each message; signals embedded (`signal_embeddings.py` generalised to messages); then a health recompute (reason `chat`)
- [ ] History analysis guard: history messages are not analysed until "Analyse history" (Admin > Teams, `POST /teams/history/analyse`), which shows the stored count and an estimated cost first (from the measured cost per message of the live analysis, or a configured estimate before any); new messages analysed as they arrive
- [ ] Tests: each node with a mocked model, the failure path, quote-not-in-message rejection, noise stopping early, indicator clearing, author role from mapping, storing and the recompute, the history guard

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (a "Chat pipeline (as built)" section; Backend rows; `> Status:`), `docs/API.md` (history analysis), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: analyse teams chat messages`

### Phase 7: Cadence, overdue actions and the two triggers (26 Nov)
**Code work**
- [ ] Health configuration `config/v2.json`: v1's values plus `gone_quiet` (5 working days, the England and Wales bank holidays for 2026 and 2027) and `missed_commitment`; `TriggerSettings` gains both; `HEALTH_CONFIG_VERSION` default `v2`
- [ ] Cadence (pure, in `app/health/`): working days since the consultant's last post; posts per week; questions to the consultant left unanswered (counted, shown, not a trigger)
- [ ] Overdue: the daily run (and every recompute) marks an open action past its due date (UK date) `overdue`
- [ ] Triggers: **gone quiet** for an active placement with a watched chat and a known consultant member, when the last consultant post is 5 or more working days back (none ever: counted from when the chat was first watched); **missed commitment** per consultant-owned overdue action (subject the action id) when the consultant has neither posted nor had a completed call since its due date; the flag shows its action (risk flags gain the action reference, or the subject key resolved on read)
- [ ] Tests: exact working-day counts across weekends and bank holidays; both triggers' hits and misses; overdue marking; the v2 configuration loaded and validated

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Health model and recompute sections; `> Status:`), `docs/API.md` (flag fields if they change), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `DEPLOYMENT.md` (the v2 configuration on staging)

**Commit checkpoint**
- [ ] `feat: add the gone-quiet and missed-commitment triggers`

### Phase 8: Messages on the pages (27 Nov)
**Code work**
- [ ] Backend: the risk board's `last_post_at` and `days_since_last_post` (the consultant's latest post); the placement health response's notable messages (those that produced a signal or action, newest first, with author role, time, class and the signals' quotes) and the chat's cadence; evidence from a message resolved to its message; the SME view keeps Technical evidence only
- [ ] Frontend: a "Last post" column on the risk board; a "Messages" section on the placement page after "Calls" (notable messages, cadence line); `EvidenceItem` shows a message's evidence as "posted <time>"; a message-sourced action reads "agreed in the chat". No Stitch round: the new pieces follow the existing table and section patterns (a judgement call for approval)
- [ ] Tests: `RiskBoard.test.tsx`, `PlacementHealthView.test.tsx`, `EvidenceItem` cases, the health view's integration tests, `placement-health.spec.ts` with a seeded message

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Health views; Risk board and Placement page rows; `> Status:`), `docs/API.md`, `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (Milestone 3 items ticked as delivered)

**Commit checkpoint**
- [ ] `feat: show teams messages on the board and placement page`

### Phase 9: Staging, exit gate, audit and handover (30 Nov – 1 Dec)
**Code work and setup**
- [ ] Every watched chat on staging listed; the history count and estimate shown; "Analyse history" pressed only on the user's say-so
- [ ] The exit gate: one real group watched for a week (from the Phase 5 rollout, so it ends inside the sprint only if Phase 5 is on staging by 2026-11-20); new posts in the database within 5 minutes; no message stored from a chat that is not watched (a query over `messages` against `teams_groups`)

**Doc updates (concurrent)**
- [ ] `ROADMAP.md` (the exit gate), `BACKLOG.md` (anything not done), `docs/tracking/SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-04-handover.md`

**Commit checkpoint**
- [ ] `docs: complete sprint 4 audit and handover`

### Alongside (not blocking)
- [ ] Real calls on staging and the PRD Phase 1 and 2 exit gates (BACKLOG High Priority)
- [ ] The Teams app's availability narrowed to the PMO team (admin action, BACKLOG)

## Spike results so far (2026-10-16)
- `Chat.Read.WhereInstalled` added to the registration by the user and admin-consented (the app's role assignments now hold it, with `Chat.ReadBasic.All`, `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All` and `Chat.Read.All`).
- Catalog id `74c9afc8-4084-4653-876f-2d63f325ada7`.
- `find`: the app-only token lists the user's chats (1,010) and finds the test chat `19:636e6d06b6e246868d954183af6900cc@thread.v2`.
- `messages` **before any install**: read OK. The read is allowed by the tenant-wide `Chat.Read.All` (still granted as the fallback), so it proves nothing about the RSC route while that permission is held.
- `install`: **HTTP 400, inner code `AppScopeIsNotAllowed`** (request `9bb3e4ba-7a0f-4953-890d-d4abcb539ba5`). A Teams app that declares only RSC permissions, with no tab or bot, cannot be installed into a group chat: the manifest must declare a capability scoped to `groupChat` (static tabs may use `groupChat` from manifest 1.16; ours is 1.30). This answers the spike's open question; the plan says stop and decide with the user.
- `members` (2026-10-16): OK, 3 members with names and Entra ids, read without any install.
- **Route decided 2026-10-16: `Chat.Read.All` for good** (see the decisions table); `subscribe --chat-id` added to the script for the per-chat subscription test.

## Judgement calls for approval with the plan
- The webhook routes are public (Graph cannot send a Bearer token), guarded by the client state, and listed as token-scoped in the route-coverage test
- `messages` keeps the body text of every message in a watched chat (the PRD's "the raw chat, kept so a flag can quote it"); system events are stored but never analysed
- The PRD's `teams_groups.kind`, `graph_team_id`, `graph_channel_id` and `delta_token` are not built: PMO groups are group chats, and chats have no delta query for an app
- Discovery runs once a day and on "Scan now" (listing two accounts' chats is not polling a resource for change at the forbidden rate)
- The placement page shows notable messages (with a signal or action), not every message; no Stitch round for the new column and section
- Sprint risk: nine phases in two weeks. The cut line, if needed: Phases 1 to 7 are the milestone; Phase 8's page work can move to Sprint 5 with the exit gate judged from Admin > Teams and the database

## Blockers and Dependencies
- (done 2026-10-16) Admin consent for `Chat.Read.WhereInstalled`; no longer needed after the route change
- (done 2026-10-16) The catalog id; no longer needed after the route change
- (answered 2026-10-16) The install through Graph: refused, `AppScopeIsNotAllowed`; route changed to `Chat.Read.All`
- The Graph certificate's values put into the app secret by the user (Phase 3)
- The week-long exit-gate watch needs Phase 5 on staging by 2026-11-20 (re-planned 2026-11-17; was 2026-10-20)
- (done 2026-10-16) Microsoft dev tunnels installed and signed in; the spike's tunnel deleted afterwards

## Session State (last updated: 2026-11-17)
- **Sprint**: 4 — Teams Chat (planned end 2026-10-27; overrun, no work between 2026-10-18 and 2026-11-17)
- **Current phase**: Phase 5 — messages in; built and tested 2026-11-17, the commit pushed, the staging rollout (`teams_enabled` true, Terraform) waiting for the user's approval
- **Phase progress**: Phases 0–4 done; Phase 4 verified on staging 2026-11-17 (see DEPLOYMENT status): f37584e deployed, task definition revision 6, discovery passing daily (160 chats, 5 linked to placements, watching off)
- **Last completed task**: Phase 4 rollout check and its records
- **Next task**: Phase 5 rollout: plan and apply `teams_enabled = true` on staging with approval, then check a test post arrives within 5 minutes; then Phase 6
- **Last commit**: f37584e "feat: add the teams tab to admin and turn on discovery in staging" (pushed)
- **Uncommitted changes**: this file and `docs/DEPLOYMENT.md` (the Phase 4 records)
- **Blockers**: none; `gh` on this Mac still needs `gh auth login` as `Abhishekkv99` (pushing and CI checks)
- **Tests passing**: 865 unit + 323 integration (backend) + 277 frontend unit + 24 e2e = 1489 at f37584e, re-run on this Mac 2026-11-17; `make lint` clean; staging `terraform plan`: no changes
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-03-handover.md` and `docs/integrations/TEAMS-GRAPH-SETUP.md` (Part D).
  - **Machine**: macOS (Apple silicon) from 2026-11-17; tools in `~/.local` (Node 22.23.5, pnpm 12.6.0 by corepack, Terraform 1.17.2, `gh` 2.104.0, the Docker CLI with Compose and Buildx plugins). Docker is Colima, not Docker Desktop: `colima start` after a reboot, and `export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock" TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` for the integration tests and compose. The local database is at migration 011. `infra/environments/staging/terraform.tfvars` (git-ignored) recreated from the live task definition.
  - **Local stack**: `docker compose up --build -d --wait`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS**: the project account is `260172548683` (profile `AdministratorAccess-260172548683` on this Mac; `aws sso login` with it). Nothing is ever deleted or overwritten in the main ITC account (`430006376054`). Region `eu-west-2`; cluster `pmo-intelligence`; logs `/ecs/pmo-intelligence-staging/*` (older than about a month are gone).
  - **Terraform**: staging state in `pmo-intelligence-tfstate-260172548683`; plan again before any apply.

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Carried from Sprint 3: the Phase 1 and Phase 2 exit gates stay in BACKLOG High Priority, alongside | User decisions 2026-10-11 and 2026-10-13 |
| Every row of "User Decisions Made" above | User decisions 2026-10-14, Sprint 4 planning; alternatives listed with each |
