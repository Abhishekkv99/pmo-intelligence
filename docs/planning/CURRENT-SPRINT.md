# Sprint 4: Teams Chat

**Status**: `in-progress` (plan approved 2026-10-14)
**Duration**: 2026-10-14 – 2026-10-27 (2 weeks)
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
| Backlog pulled in (2026-10-14) | **All four**: the risk board's project in its own column; the `sessions.spec.ts` seed (a decodable WebM, the cold-start allowance on the retry test); remove the unused `.chart-animate` CSS; mypy strict on the backend tests, with `make lint` and CI widened to `app tests` | Any subset |
| Graph certificate (2026-10-14) | **In the app secret**: two new keys in `pmo-intelligence/staging/app` (`GRAPH_CERTIFICATE_PFX_BASE64`, `GRAPH_CERTIFICATE_PASSWORD`), injected as environment variables; Terraform adds the key names, the values are put with `put-secret-value` | A separate secret |
| Start (2026-10-14) | **A spike on the tenant first**: a script installs the app into one test chat titled `PRJ ITC TEST …`, reads it with RSC, and creates and validates one `installedToChats` subscription; the build phases start only once it works; if it fails, stop and decide | Build and test as we go |

| Pipeline unit (2026-10-14) | **One job per chat, batched**: a notification queues the chat's job (the queue merges repeats); the job takes every unanalysed message in the chat, with the messages before them as context, classifies them in one call, drops noise, and extracts from the rest | One run per message |
| Catalog id (2026-10-14) | **A one-off lookup kept as a setting**: a signed-in person runs `appCatalogs/teamsApps?$filter=externalId eq '0f2eaf35-928a-4321-9261-692893f270ff'` in Graph Explorer during the spike; the id goes into `TEAMS_CATALOG_APP_ID`. No new permission | Request `AppCatalog.Read.All` |
| Cost guard (2026-10-14) | **Count first, a person confirms**: watching a chat stores its whole history at once; analysing stored history waits until Admin > Teams shows the message count and an estimated LLM cost and a PMO manager presses "Analyse history". New messages are analysed as they arrive | A monthly cap; no guard |
| Placement ends (2026-10-14) | **Remove the app, keep the data**: the app removes itself from the chat (the chat shows it), so nothing more is read; stored messages and signals stay (retention is product Phase 5); an extension adds it back | Stop processing but stay installed; keep watching until turned off |

## Task Checklist

>>> CURRENT PHASE: Phase 0 (plan awaiting approval)

Every phase: re-read this plan, code and tests, the doc list walked item by item, the commit checkpoint, then stop. Backend: `make test-backend` with `-rf`; frontend Vitest with `--maxWorkers=4`; e2e with one worker after `docker compose up --build -d --wait <changed service>`. Every Graph call in tests is mocked (an `httpx` mock transport); no test calls Microsoft. Test data uses made-up names only: real chat titles name real consultants, so the title shapes are reproduced with invented names. Every push: both CI filters read before saying what it runs and deploys, and the deploy recorded in DEPLOYMENT's status in the next commit.

### Phase 0: Plan
**Code work**
- [x] Plan approved (2026-10-14, with its judgement calls)

**Doc updates (concurrent)**
- [x] This file; `ROADMAP.md` (Milestone 3 dated Sprint 4, the webhook replacing the poll noted); `BACKLOG.md` (the four pulled items marked for Sprint 4; open question 4 notes the webhook and `Chat.Read.WhereInstalled`)

**Commit checkpoint**
- [ ] `docs: plan sprint 4`

### Phase 1: Spike on the tenant (scripts only, nothing deployed)
**Setup (the user and the tenant admin)**
- [ ] `Chat.Read.WhereInstalled` added to the Graph app registration (`az ad app permission add`, with the user's go-ahead) and admin consent requested (the request text added to `TEAMS-GRAPH-SETUP.md`)
- [ ] The catalog id looked up in Graph Explorer by a signed-in person and recorded
- [ ] A test group chat titled `PRJ ITC TEST - <made-up name> - <made-up client> - 1/10/2026 - 31/3/2027` with the user and one colleague

**Code work**
- [ ] `scripts/teams/spike_chat_route.py` (run with `uv run --with msal --with requests`, certificate as in `verify_chat_access.py`): (1) add the app to the test chat (`POST /chats/{id}/installedApps` with the RSC permission set); (2) list its members (`ChatMember.Read.Chat`); (3) read its messages (`ChatMessage.Read.Chat`), printing ids, times, types and author ids only, never content; (4) create one subscription to `installedToChats/getAllMessages` without resource data, pointing at a local receiver; (5) remove the app again (`DELETE installedApps`), confirming the "placement ends" path
- [ ] `scripts/teams/spike_receiver.py`: a local HTTP receiver that answers the validation token and logs each notification's subscription id, change type and resource path only, reached through a temporary tunnel (Microsoft dev tunnels) for the length of the spike
- [ ] Results: install works (or the exact error) while the app shows "not available"; an RSC-only package installs; a test post's notification arrives and how fast. **If the install or the subscription fails, stop and decide with the user before Phase 3**

**Doc updates (concurrent)**
- [ ] `docs/integrations/TEAMS-GRAPH-SETUP.md` (a "Part D: spike" with steps and results; the results table: catalog id, `Chat.Read.WhereInstalled`, install and notification results), `FEATURES.md` (the spike scripts as operator tools), `CHANGELOG.md` (README: no new make target)

**Commit checkpoint**
- [ ] `chore: add the chat route spike scripts`

### Phase 2: Backlog clean-ups (independent; can run while the admin consent is awaited)
**Code work**
- [ ] Risk board: `client` and `project` as separate columns in `RiskBoard.tsx`; the search and the client filter unchanged
- [ ] `sessions.spec.ts` seed: a small decodable WebM in `app/cli/seed_e2e_session.py`, and the cold-start allowance (`test.setTimeout`) on the retry test
- [ ] Remove `.chart-animate` and its delay classes from `globals.css` (and its reduced-motion block), after `git grep` shows no user
- [ ] mypy strict on `tests`: fix the 57 errors in 8 test files; `make lint` and the CI mypy step widened to `app tests`
- [ ] Tests: `RiskBoard.test.tsx` (the two columns); e2e 23 of 23 with one worker, then `sessions.spec.ts` three times alone; `uv run mypy app tests` clean

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Risk board row; CI table's mypy step; `> Status:`), `DESIGN.md` (risk board columns; the chart entrance removed), `BACKLOG.md` (the four items ticked), `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`, `DEPLOYMENT.md` status for the push (README: `make lint` row if its description changes)

**Commit checkpoint**
- [ ] `test: type-check the backend tests` and `feat: show the risk board's project in its own column` (two commits; the seed and CSS fixes with the second, or as `fix:`/`chore:` if the user prefers)

### Phase 3: Data model, settings and the Graph client
**Code work**
- [ ] `app/models/enums.py`: `MessageClass` (the PRD's classes: consultant update, question, stakeholder context, praise, concern, escalation, administrative, noise, with meanings for the prompts), `TeamsChatMatch` (`matched`, `chosen`, `needs_choice`, `unmatched`, `unparsed`), `TeamsWatchState` (`not_watched`, `installing`, `watching`, `removed`, `failed`), `HistoryState` (`none`, `stored`, `analysing`, `analysed`), `SnapshotReason.CHAT`
- [ ] Migration 010: `teams_groups` (`graph_chat_id` unique, `title`, the parsed title fields, `placement_id`, match status and candidates, `consultant_member_oid` and its match status, watch state, `installed_at`, `removed_at`, `sync_requested_at`, `last_synced_at`, `last_message_at`, history state, `error_message`), `messages` (`teams_group_id`, `graph_message_id` unique with the group, `author_entra_oid`, `author_name`, `author_role`, `posted_at`, `last_modified_at`, `deleted_at`, `body_text`, `reply_to_message_id`, `message_type`, `message_class`, `is_noise`, `is_history`, `analysed_at`), `graph_subscriptions` (`subscription_id`, `resource`, `expires_at`), the FK `processing_costs.message_id` → `messages`, and the snapshot reason's CHECK; the PRD's `kind`/`graph_team_id`/`delta_token` columns not built (group chats only, no delta for chats)
- [ ] `app/config.py`: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CERTIFICATE_PFX_BASE64`, `GRAPH_CERTIFICATE_PASSWORD`, `GRAPH_CLIENT_STATE` (the webhook secret), `TEAMS_CATALOG_APP_ID`, `TEAMS_DISCOVERY_ACCOUNTS`, `TEAMS_ENABLED` (off by default), `TEAMS_NOTIFICATION_BASE_URL`; `.env.example`
- [ ] `app/services/teams/graph_client.py`: msal certificate token (cached until expiry), one `httpx.AsyncClient` with a finite timeout and an injectable transport, paging through `@odata.nextLink`, `Retry-After` and exponential backoff on 429, 503 and 504, pacing under the per-chat 1 rps; any failure a `GraphError`. `uv add msal` (mypy override if untyped)
- [ ] Infra: `app_secret_keys` gains the Graph secrets and `GRAPH_CLIENT_STATE`; the non-secret ids in the backend environment; `teams_enabled` module variable (false until Phase 5's rollout). Terraform plan shown, applied only with approval (replaces the backend task definition, so the backend redeploys); the values put with `put-secret-value` by the user
- [ ] Tests: migration up and down; the Graph client (token reuse, paging, `Retry-After`, backoff limit, error mapping) on a mock transport; settings

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Data Model: migration 010 with differences from the draft; Backend rows for Settings, Enumerations, the Graph client; Infrastructure; `> Status:`), `DEPLOYMENT.md` (a new section "12. Teams chat (Graph secrets, catalog id)"; status), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the teams chat data model and graph client`

### Phase 4: Discovery, title matching, watching and Admin > Teams
**Code work**
- [ ] `app/services/teams/chat_titles.py`: the tolerant parser (hyphen or en dash with or without spaces, `PRJ ITC-` and `PRJ ITC - <stack> -`, dates `D/M/YYYY`, `D/M/YY`, `D-M-YY`, `YYYY-MM-DD`, in brackets or not, a missing or extra part reported); the quick add's `parse_line` left as it is
- [ ] Matching (`chat_match.py`): client by normalised name, consultant with `name_match.match_folder` (first or last name), placement by consultant, client and start date (any of the client's projects); exactly one is `matched`, else `needs_choice` or `unmatched`; `matched` and `chosen` never changed by a later scan
- [ ] Discovery job (`teams_discovery`, fixed id, backlog priority): lists `TEAMS_DISCOVERY_ACCOUNTS`' chats (`Chat.ReadBasic.All`), keeps `PRJ ITC` titles, merges by chat id, upserts `teams_groups`, re-matches the undecided ones; once a day (the loop pattern of `recordings/periodic.py`) and on "Scan now"
- [ ] Watch policy (`teams_watch` job per chat): a chat linked to an active placement whose end date has not passed is watched: the app added (`POST installedApps`), its members read and the consultant matched by name (a single match sets `consultants.entra_oid`; otherwise Admin asks); a watched chat whose placement ended or whose end date passed has the app removed (`DELETE installedApps`) and keeps its data; re-evaluated after discovery, a register edit and the daily run
- [ ] Routes (`app/api/v1/teams.py`, `pmo_manager` and `admin`; `{chat_id}` routes under `require_roles`, the coverage test extended like `{folder_id}`): `GET /teams/chats` (with the last scan), `POST /teams/scan`, `PUT /teams/chats/{chat_id}/placement`, `POST /teams/chats/{chat_id}/placement` (create from the title through the quick add's writer, the line prefilled and editable), `PUT /teams/chats/{chat_id}/consultant-member`
- [ ] Admin > Teams tab (`components/admin/teams/TeamsTab.tsx`, `hooks/useTeamsChats.ts`): the last scan and Scan now; every `PRJ ITC` chat with its title, match, placement, watch state, consultant member, last message and history state; pickers for the placement and the consultant member; "Create placement from title"; polls like the Recordings tab
- [ ] Tests: the parser on every title shape seen (made-up names); matching; discovery and watch jobs on a mock transport (install, remove, member match, failure recorded); every route called and its response read; `TeamsTab.test.tsx`; an Admin e2e (the tab lists seeded chats; links one)

**Doc updates (concurrent)**
- [ ] `docs/API.md` (Teams section), `ARCHITECTURE.md` (Backend and Frontend rows; a "Teams chat (as built)" section; `> Status:`), `DESIGN.md` (the Teams tab), `TEAMS-GRAPH-SETUP.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: find, match and watch the pmo group chats`

### Phase 5: Messages in: history, webhook, subscription and catch-up
**Code work**
- [ ] History: when a chat becomes watched, its whole history is read once (`GET /chats/{id}/messages`, paced) and stored (HTML to plain text; system events stored as such and never analysed; deletions kept as `deleted_at` with the text cleared), marked `is_history`; the chat's history state becomes `stored`
- [ ] Webhook (`POST /teams/notifications` and `POST /teams/lifecycle`, public, guarded by `require_graph_client_state`, listed as token-scoped in the coverage test): answers the validation token as text/plain; checks `clientState` in constant time; for each notification records `sync_requested_at` on its chat and queues the chat's sync job (`CHAT_PRIORITY`); answers 202 at once; a notification for a chat not watched is dropped and logged
- [ ] Sync job (`teams_sync`, one per chat): reads messages changed since the chat's watermark (`lastModifiedDateTime gt`), stores new, edited and deleted ones, queues the chat's analysis; a sync is triggered only by a notification, the daily catch-up or a lifecycle `missed`, never on a timer, so the polling rule holds
- [ ] Subscription manager: creates the one `installedToChats` subscription when absent, renews it a day before its three-day expiry, re-authorises on `reauthorizationRequired`, recreates on `subscriptionRemoved`, and on `missed` queues a sync of every watched chat; a daily catch-up sync of every watched chat (one date-ranged read each)
- [ ] Takeover step: chats whose `sync_requested_at` is newer than `last_synced_at` are queued again (a notification taken by the non-owner task during a deploy is not lost); counts logged, zero included
- [ ] Rollout to staging: `teams_enabled` true (Terraform, with approval); the subscription created; the test chat checked (a post appears in the database within 5 minutes)
- [ ] Tests: validation echo, client state refused, notification to job, sync (new, edited, deleted, system event), history paging, subscription create, renew and lifecycle events, takeover requeue

**Doc updates (concurrent)**
- [ ] `docs/API.md` (the notification routes), `ARCHITECTURE.md` (Teams chat section; Infrastructure; `> Status:`), `DEPLOYMENT.md` (section 12: turning it on, checking the subscription; status), `TEAMS-GRAPH-SETUP.md` ("Engineering notes" updated: webhook, not polling), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: receive teams chat messages through change notifications`

### Phase 6: Chat pipeline
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

### Phase 7: Cadence, overdue actions and the two triggers
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

### Phase 8: Messages on the pages
**Code work**
- [ ] Backend: the risk board's `last_post_at` and `days_since_last_post` (the consultant's latest post); the placement health response's notable messages (those that produced a signal or action, newest first, with author role, time, class and the signals' quotes) and the chat's cadence; evidence from a message resolved to its message; the SME view keeps Technical evidence only
- [ ] Frontend: a "Last post" column on the risk board; a "Messages" section on the placement page after "Calls" (notable messages, cadence line); `EvidenceItem` shows a message's evidence as "posted <time>"; a message-sourced action reads "agreed in the chat". No Stitch round: the new pieces follow the existing table and section patterns (a judgement call for approval)
- [ ] Tests: `RiskBoard.test.tsx`, `PlacementHealthView.test.tsx`, `EvidenceItem` cases, the health view's integration tests, `placement-health.spec.ts` with a seeded message

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Health views; Risk board and Placement page rows; `> Status:`), `docs/API.md`, `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (Milestone 3 items ticked as delivered)

**Commit checkpoint**
- [ ] `feat: show teams messages on the board and placement page`

### Phase 9: Staging, exit gate, audit and handover
**Code work and setup**
- [ ] Every watched chat on staging listed; the history count and estimate shown; "Analyse history" pressed only on the user's say-so
- [ ] The exit gate: one real group watched for a week (from the Phase 5 rollout, so it ends inside the sprint only if Phase 5 is on staging by 2026-10-20); new posts in the database within 5 minutes; no message stored from a chat that is not watched (a query over `messages` against `teams_groups`)

**Doc updates (concurrent)**
- [ ] `ROADMAP.md` (the exit gate), `BACKLOG.md` (anything not done), `docs/tracking/SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-04-handover.md`

**Commit checkpoint**
- [ ] `docs: complete sprint 4 audit and handover`

### Alongside (not blocking)
- [ ] Real calls on staging and the PRD Phase 1 and 2 exit gates (BACKLOG High Priority)
- [ ] The Teams app's availability narrowed to the PMO team (admin action, BACKLOG)

## Judgement calls for approval with the plan
- The webhook routes are public (Graph cannot send a Bearer token), guarded by the client state, and listed as token-scoped in the route-coverage test
- `messages` keeps the body text of every message in a watched chat (the PRD's "the raw chat, kept so a flag can quote it"); system events are stored but never analysed
- The PRD's `teams_groups.kind`, `graph_team_id`, `graph_channel_id` and `delta_token` are not built: PMO groups are group chats, and chats have no delta query for an app
- Discovery runs once a day and on "Scan now" (listing two accounts' chats is not polling a resource for change at the forbidden rate)
- The placement page shows notable messages (with a signal or action), not every message; no Stitch round for the new column and section
- Sprint risk: nine phases in two weeks. The cut line, if needed: Phases 1 to 7 are the milestone; Phase 8's page work can move to Sprint 5 with the exit gate judged from Admin > Teams and the database

## Blockers and Dependencies
- Admin consent for `Chat.Read.WhereInstalled` (tenant admin): needed for the spike's subscription step and Phase 5
- The catalog id of the Teams app "PMO Intelligence" (a one-off lookup by a signed-in person)
- Whether an install through Graph works while the app shows "not available" (spike)
- The Graph certificate's values put into the app secret by the user (Phase 3)
- The week-long exit-gate watch needs Phase 5 on staging by 2026-10-20

## Session State (last updated: 2026-10-14 12:00)
- **Sprint**: 4 — Teams Chat
- **Current phase**: Phase 0 — plan approved 2026-10-14; doc updates done, commit checkpoint
- **Last completed task**: every planning question answered (16 decisions above); the task checklist written
- **Next task**: the `docs: plan sprint 4` commit (awaiting the user), then Phase 1 (the spike) once asked to continue
- **Last commit**: b4efa3a "docs: record the chat discovery results and the granted permissions", pushed 2026-10-14
- **Uncommitted changes**: this file (Sprint 3's version is in git at b4efa3a), `ROADMAP.md`, `BACKLOG.md`
- **Blockers**: none for planning
- **Tests passing**: 763 unit + 282 integration (backend) + 265 frontend unit; 23 e2e = 1333 (unchanged since Sprint 3)
- **Files modified this session**: this file, `docs/planning/ROADMAP.md`, `docs/planning/BACKLOG.md`
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-03-handover.md` and `docs/integrations/TEAMS-GRAPH-SETUP.md` (Part C).
  - The discovery script of 2026-10-14 is not in the repo (it lived in an earlier session's scratchpad).
  - **Local stack**: `docker compose up --build -d --wait`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS sign-in**: `aws sso login --profile pmo-intelligence`. Nothing is ever deleted or overwritten in the main ITC account (`430006376054`).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Carried from Sprint 3: the Phase 1 and Phase 2 exit gates stay in BACKLOG High Priority, alongside | User decisions 2026-10-11 and 2026-10-13 |
| Every row of "User Decisions Made" above | User decisions 2026-10-14, Sprint 4 planning; alternatives listed with each |
