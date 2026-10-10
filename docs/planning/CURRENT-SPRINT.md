# Sprint 2: Health v1

**Status**: `in-progress` (plan approved 2026-10-09)
**Duration**: 2026-10-12 – 2026-10-23 (2 weeks)
**Objective**: PRD Phase 2. Turn signals into a deterministic health reading per placement: signal embeddings, the scoring module, health snapshots, triggers and risk flags, the daily recompute, the risk board and the placement (consultant) page. Also the processing takeover delay after backend deploys (BACKLOG tech debt). Real calls are processed on staging alongside the build.
**Exit gate** (PRD Phase 2): ten placements scored from their sessions; the PMO manager agrees with the ranking, or the weights are tuned until they do.
**Branch**: `develop`
**Previous sprint**: Sprint 1 (Register and Sessions), complete 2026-10-09 without its exit gate; see `docs/handover/sprint-01-handover.md`. Its plan, session notes and Decisions Log are in git history (`957e497`, plus the last row carried into this Decisions Log).

---

## Research Findings Summary
- **Takeover delay** (BACKLOG tech debt, 370–390 s on four deploys):
  - The backend target group (`infra/modules/environment/alb.tf`) sets no `deregistration_delay`, so AWS's default 300 s applies; the ECS container definition sets no `stopTimeout` (default 30 s). `processing_ownership.py`'s own docstring names the 300 s deregistration delay before the old task is signalled.
  - The backend runs uvicorn in exec form (`backend/Dockerfile`), so SIGTERM reaches it; the lifespan stops the queue and calls `release()` on the lock's own connection, but `release()` logs nothing, so a clean release cannot be told from a dropped connection.
  - A second fit: RDS for PostgreSQL keepalive defaults are `tcp_keepalives_idle` 300 s, `interval` 30 s, `count` 2 (AWS, "Dead connection handling in PostgreSQL"), about 6 minutes to drop a silent peer.
  - Phase 1 reads the old task's stop timestamps and shutdown log before choosing the fix.
- **Embeddings**: text-embedding-3-small is GA on Azure OpenAI until 2028-02-09 (Microsoft Foundry model retirement schedule, updated 2026-09-23); a third-party page claiming an April 2026 deprecation is wrong. gpt-5.4-mini (2026-03-17) is GA until 2027-09-21. 1536 dimensions fit pgvector's HNSW limit (2,000); OpenAI's embeddings are unit-normalised, so cosine distance (`<=>`, `vector_cosine_ops`) is the operator. Interview Intelligence uses HNSW `m=16, ef_construction=64` and `SET LOCAL hnsw.ef_search` before a search. The staging secret already holds `AZURE_EMBEDDING_DEPLOYMENT` (`text-embedding-3-small-staging`). Data Zone Standard is about $0.022–0.024 per 1M tokens (third-party tracker), near the cost tracker's $0.02.
- **Time-decayed scores**: the standard form is weight = 0.5^(age/half-life), normalised by the sum of weights (polars `ewm_mean_by`, ClickHouse `exponentialTimeDecayedAvg`). A known pitfall is that a decayed average swings on little data when few signals are recent; a prior with its own weight in the average damps that, which is the formula chosen below.
- **Charts**: Recharts 2.15.4 and the shadcn `components/ui/chart.tsx` wrapper are installed and unused. The shadcn chart colours come from `--chart-1`…`--chart-5`, redefined under `.dark`; reference lines and dots take `var(--…)` colours to follow the theme. Recharts 3.x on React 19 has had an immer issue and prefers the `responsive` prop to `ResponsiveContainer`; staying on 2.15.4 this sprint avoids a migration.
- **Code found to reuse**:
  - `llm_factory.build_embeddings()` (cached, unused) and `cost_tracker.calculate_embedding_cost()`.
  - `services/recordings/periodic.py` is the pattern for a loop that enqueues a fixed-id queue job; there is no daily scheduler yet. Interview Intelligence's daily report scheduler checks the hour in UTC and keeps its "sent" date in memory, so it is not copied.
  - The route commits, then queues (`api/v1/sessions.py`).
  - `session_repo` already applies `ListScope` in a query; `placement_repo._rows` takes a filter easily.
  - `ExtractedSignal` (`app/ai/session/schemas.py`) is shared by the client and relationship/engagement nodes, so `indicator` goes in one place; `prompts/common.py` lists the meanings the prompts quote.
  - The e2e auth setup checks the `h2` "Risk board" on `/`, so the new board keeps it.

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|
| Sprint scope | All of PRD Phase 2 plus the takeover delay fix | Phase 2 only; split over two sprints (backend, then pages) |
| Real calls (handover Priority 1) | Alongside, not blocking: build on mocked and seeded data, review real runs as they come, prompt fixes as their own commits; the exit gate needs them | A first, blocking phase; not this sprint |
| SME scope (BACKLOG #5) | Sessions and the Technical dimension only, as the PRD suggests; the API leaves out overall, RAG, flags and the other dimensions for an SME. PS and tech lead see full health for their placements; the global roles see everything | Same as PS and tech lead; sessions only, no health |
| Weights and thresholds (BACKLOG #7) | The PRD's values as v1: Delivery 30 %, Relationship 25 %, Technical 15 %, Engagement 15 %, Communication 10 %, Onboarding 5 % (25 % in the first 30 days, the others scaled down); half-life 14 days; green ≥ 7, amber 5–6.9, red < 5; trigger thresholds as in the PRD | PRD values with Communication off until chat; other values |
| Dimension score | Decayed average with a prior: score = (P·prior + Σ wᵢvᵢ) / (P + Σ wᵢ), wᵢ = confidence × 0.5^(age days / 14), prior 7.0 with weight P = 1.0; value positive 9, neutral 7, negative 5 / 3 / 1 for severity 1 / 2 / 3; all numbers configuration | Plain decayed average; baseline plus points |
| No evidence | A placement with no signals is "Not scored" (no overall, trend or RAG) and listed last; contract horizon still opens flags | Prior score (7.0, green) |
| Trend | Overall now minus the overall the same function gives from the signals known 14 days ago; flat within ±0.5 | Compare with a stored snapshot |
| Configuration | A versioned JSON file in the repo, validated by Pydantic, chosen by `HEALTH_CONFIG_VERSION`; each snapshot records `weights_version` | Environment settings; a database table with an admin page |
| Triggers this sprint | Client dissatisfaction, intent to leave (critical); repeated blocker, downward trend, relationship strain, contract horizon (high). Gone quiet and missed commitment come with Teams chat (Phase 3) | Six plus missed commitment; all eight |
| Critical detection | A nullable `signals.indicator` (`client_dissatisfaction`, `consultant_change_requested`, `intent_to_leave`), chosen by the client and relationship/engagement nodes with the quote as evidence; no real call has been analysed, so nothing is re-analysed | Inferred from dimension and severity |
| Flags | Open only this sprint (closing with a note is Phase 4); at most one open flag per placement, trigger and subject; new evidence is added to it | Pull closing in now |
| Embeddings | Filled in the session job after the signals are stored (non-fatal, costed), a backfill command and an HNSW cosine index; no search UI yet | Fill and show similar signals; defer |
| Consultant page | Per placement, `/placements/{id}`, titled with the consultant; links to their other placements; logged placement scope | Per consultant |
| Board column for "last post" | Days since the last processed call until Teams chat lands | Leave it out until Phase 3 |
| Recompute | After every analysed call, after a placement or project edit or an import, and daily at 06:00 Europe/London for every active placement, as queue jobs | Call and daily only |
| Health chart | Stored snapshots, with call markers | A recomputed daily series |
| SME on the board | The placements naming them, with the Technical score and trend only | No board for SMEs |
| Snapshot evidence | Each snapshot stores, per dimension, the top five contributing signals (id, weight, value) and the counts | Recompute on read |
| Repeated blocker | An open issue with at least one Technical signal, seen in 2+ calls or open more than 10 days | Any open issue |
| Dates | 2026-10-12 – 2026-10-23 | From today; three weeks |
| Trend basis (after the design review) | "Signals known 14 days ago" means signals whose call happened on or before now − 14 days, decayed as of that day, so a backlog processed today still shows its trend | By when the signal was stored |
| SME leaks (after the design review) | Closed both: an SME's board sorts by Technical score, then name, with no risk filter, so its order does not reveal the overall ranking; the session page shows an SME only Technical signals (transcript, summary, issues and actions unchanged) | Board only; neither |
| Queue re-run (after the design review) | The processing queue remembers a key requested while that job runs and queues it once more when it finishes, for every job kind, so an edit made during a recompute is not lost | Health jobs only; accept the gap until the daily run |
| Scoring lookback (Phase 2) | Signals whose call was within 90 days of the scoring time count (a 90-day-old signal weighs 1 % of a fresh one); none in 90 days is "Not scored" | 180 days; no window |
| Flag windows (Phase 2) | Client dissatisfaction and intent to leave fire on a tagged signal anywhere in the 90-day lookback; relationship strain counts only signals within 14 days, for the single severity 3 and for the pair | 14 days for all; the lookback for all |
| Trend without a past score (Phase 2) | No trend ("—") and no downward-trend flag until there is a score 14 days back | Compare with the prior 7.0 |
| Precision (Phase 2) | Every score rounded half up to one decimal and stored that way; RAG, trend and triggers compare the rounded values | Two decimals stored, one shown |
| Contract horizon past its end (Phase 2) | An active placement whose expected end is today + 30 days or earlier, past dates included, without a confirmed extension | Only upcoming ends |
| Relationship strain pair (Phase 2) | Two negative Relationship signals of severity 2 or more within 14 days | Exactly severity 2 |
| Top contributors (Phase 2) | Ranked by weight × \|value − prior\| (the pull from 7.0), neutral never, the newer first on a tie | By weight alone |
| Embeddings client (after the design review) | The `openai` package's `AsyncAzureOpenAI.embeddings.create` with the same endpoint, key and deployment: exact token usage for the cost row and no tokenizer download in the non-root container; the unused `build_embeddings()` is replaced | LangChain's `AzureOpenAIEmbeddings` with an estimated cost and the tokenizer baked into the image |

## Task Checklist

>>> CURRENT PHASE: Phase 6 (not started; Phase 5 committed)

### Phase 0: Plan
- [x] Plan approved (2026-10-09)
- [x] Commit `docs: plan sprint 2` (0529a6b)

### Phase 1: Processing takeover delay
**Code work**
- [x] Investigate (read-only): the last backend deploy's old task (`aws ecs describe-tasks`: stoppingAt, stoppedAt, stopCode) and its CloudWatch log at shutdown (uvicorn "Shutting down", "Waiting for application shutdown", "Processing queue stopped") against the new task's "Took processing ownership after Xs"; decide between the deregistration delay and the keepalive explanation (2026-10-09, from the service events and logs, since stopped tasks are kept only about an hour. Deploy of 530df1d, UTC: new task waiting from 13:31:37; old task deregistered and draining from 13:32:15; old task signalled 13:37:49.6 and shut down cleanly in 0.1 s ("Processing queue stopped", "Application shutdown complete"); new task "Took processing ownership after 375s" at 13:37:52.8. **The drain is the whole delay**; the keepalive explanation is ruled out, and Sprint 1's "the old task's log has no shutdown lines" was wrong: the lines were there)
- [x] Fix, agreed with the user against the evidence (user decisions 2026-10-09: drain 60 s; `stopTimeout` left at the default 30 s, since shutdown takes 0.1 s and the queue's grace is 10 s; so no uvicorn graceful-shutdown change, no lifespan log line beyond the release line, and the "ECS allows 30 s" comments stay true; only `processing_ownership.py`'s docstring changed): backend target group `deregistration_delay` (`infra/modules/environment/alb.tf`); backend container `stopTimeout` (`ecs.tf`, at most 120 on Fargate) so the queue stop and the release finish before SIGKILL; INFO lines in `ProcessingOwnership.release()` and the lifespan shutdown; uvicorn `--timeout-graceful-shutdown` below `stopTimeout` if needed (`backend/Dockerfile`); correct the docstrings that cite 300 s and 30 s (`processing_ownership.py`, `processing_queue.py`, `main.py`). A shorter deregistration delay also cuts in-flight requests, uploads included (up to 500 MB through the backend), at a deploy: weigh it with the user before choosing the value
- [x] Terraform plan, `git status --untracked-files=all infra/`, approval, apply; one redeploy read through to "Took processing ownership" with the wait recorded (`tfplan-drain`: 0 add, 1 change in place, 0 destroy; approved and applied 2026-10-09; the target group reads `deregistration_delay.timeout_seconds` 60; staging still 61 managed resources; plan file deleted. Deploy of fd2cd77, CI run 37964809513 green: "Took processing ownership after 150s" (was 375 s); the old task stopped cleanly, without the release line since it ran the previous image)
- [x] Tests: the release log line (`test_release_logs_only_when_it_gave_the_lock_up`; backend 624 unit and 202 integration pass; ruff, format and mypy clean)

**Doc updates (concurrent)**
- [x] `DEPLOYMENT.md` (deploy timing, `> Status:`), `ARCHITECTURE.md` (infrastructure, `> Status:`), `BACKLOG.md` (tick), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (DEPLOYMENT: "What a backend deploy does to processing" under "Redeploying without a change"; README: no new make target)

**Commit checkpoint**
- [x] `fix: hand over processing promptly on deploy` (fd2cd77, pushed with 0529a6b)

### Phase 2: Health tables, enumerations, configuration, scoring and triggers
**Code work**
- [x] `app/models/enums.py`: `Indicator` with `INDICATOR_MEANINGS`, `RiskLevel` (green, amber, red), `Trend` (up, flat, down), `RiskTrigger` (all eight PRD triggers; six evaluated now), `FlagSeverity` (medium, high, critical) and the trigger severities (as `SignalIndicator` with `SIGNAL_INDICATOR_MEANINGS`, deviation: the name says what it tags; also `RISK_TRIGGER_MEANINGS`, `RISK_TRIGGER_SEVERITY` and `SnapshotReason`: call, register, daily, catch_up)
- [x] Migration `006` and `app/models/health.py`: (`006_create_health_snapshots_and_risk_flags.py`, written by hand since the dev database was down; `evidence_signal_ids` is a `uuid[]`)
  - `health_snapshots`: placement, computed_at, the six dimension scores, overall, trend, trend delta, risk level (empty when not scored), scored, signal count, `weights_version`, reason (call, register, daily), `evidence` JSONB (per dimension: the top five signals with weight and value, and the count); index on (placement, computed_at)
  - `risk_flags`: placement, trigger, severity, subject key (not null, `''` when the trigger has no subject, since NULLs never clash in a unique index), opened_at, `evidence_signal_ids`, closed_at, closed_by_user_id, closing_note; one open flag per (placement, trigger, subject key) by a partial unique index. With no closing this sprint, an open critical flag keeps its placement at least amber until Phase 4
  - `signals.indicator` (nullable, checked); an HNSW index on `signals.embedding` (`vector_cosine_ops`, m 16, ef_construction 64)
- [x] Model and migration declare the HNSW index identically (ops and `WITH` options), so `alembic check` stays clean; `EXPECTED_TABLES` and the meanings test cover the new tables and enumerations (`alembic check` clean in `test_migrations.py`; a 006 up-and-down case)
- [x] `app/health/` (pure, no database, `now` passed in): `config.py` (`HealthConfig`, `load_health_config`), `config/v1.json`, `scoring.py` (`score_placement`: dimension scores, onboarding weighting by days since start, overall, trend from the signals whose call is on or before now − 14 days, decayed as of then, RAG with the critical floor, contributors), `triggers.py` (`evaluate_triggers`); settings `HEALTH_CONFIG_VERSION`, `HEALTH_DAILY_ENABLED`, `HEALTH_DAILY_HOUR`, `HEALTH_TIMEZONE` (user decisions 2026-10-09 in the Decisions Log: 90-day lookback, flag windows, no trend without a past score, one decimal everywhere, past contract ends fire, strain pairs of severity 2 or more, contributors by pull from the prior; `round1`, `score_at`, `assess`, `trend_between`, `risk_level`, `evaluate_triggers`)
- [x] Tests: exact scores for fixed signal sets (prior, decay, confidence, the onboarding window, weights scaled), not scored, trend bands, RAG and the critical floor, each trigger at its edges, configuration validation; migration 006 up and down; constraints (unit: `test_health_scoring.py` 42 with hand-worked numbers, `test_health_triggers.py` 29, `test_health_config.py` 15; integration: `test_health_schema.py` 17, a 006 case in `test_migrations.py`; backend 710 unit and 220 integration pass; ruff, format and mypy clean)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (health model as built, migration 006, `> Status:`), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (new section "Health model (as built)"; README: no new make target; `DEPLOYMENT.md`'s status waits for the deploy that applies 006, as before)

**Commit checkpoint**
- [x] `feat: add the health scoring module and its tables` (385af31; CI run 37968905020 green; migration 006 applied on staging; ownership taken after 105 s, the old task's release line logged)

### Phase 3: Indicator tagging and signal embeddings
**Code work**
- [x] `ExtractedSignal.indicator` (`app/ai/session/schemas.py`, not on `Evidence`, which issues share); `prompts/common.py` lists `INDICATOR_MEANINGS` for the client and relationship/engagement prompts; `drafts.py` and `emit.py` carry it, allowing `client_dissatisfaction` and `consultant_change_requested` from the client node and `intent_to_leave` from the relationship/engagement node, and keeping an indicator when the same-quote dedup drops its duplicate; `session_analysis.py` stores it (the meanings are `SIGNAL_INDICATOR_MEANINGS`; which node may set which is `SIGNAL_INDICATORS_BY_CATEGORY` in `enums.py`, read by the prompts and emit)
- [x] `app/services/signal_embeddings.py`: embed a session's signals (quote and note) with `AsyncAzureOpenAI.embeddings.create` (replacing the unused `build_embeddings()`) after the analysis commit, only for a `completed` session, in its own try/except so a failure never fails the session; a `processing_costs` row from `usage.total_tokens`; `signal_repo` reads and writes; `app/cli/backfill_signal_embeddings.py` (NULL embeddings, batched); confirm the staging secret's `AZURE_EMBEDDING_DEPLOYMENT` and the Azure deployment (2026-10-10: the secret names `text-embedding-3-small-staging`, which `oai-pmo-intelligence-swc` has, DataZoneStandard, Succeeded; `build_embedding_client()` replaces `build_embeddings()`; settings `SIGNAL_EMBEDDING_BATCH_SIZE`, `SIGNAL_EMBEDDING_TIMEOUT_SECONDS`)
- [x] `make backfill-embeddings ENV=<env>` and `scripts/backfill-embeddings.sh`: a one-off task from the backend's task definition with the command overridden (it has the Azure settings; `admin-cli` has only `DATABASE_URL`), so no Terraform change (user decision 2026-10-10; the task definition and log group are read from the service, checked read-only on staging 2026-10-10: `pmo-intelligence-staging-backend:3`, `/ecs/pmo-intelligence-staging/backend`; not run yet, as the image lacks the command until this phase deploys)
- [x] Tests: prompts list the meanings, emit and analysis keep the indicator; embeddings with a mocked client (success, failure non-fatal, cost row); the backfill command (unit: `test_session_emit.py` +8, `test_session_prompts.py` +4, `test_backfill_signal_embeddings_cli.py` 4, `test_llm_factory.py` rewritten for the new client; integration: `test_signal_embeddings.py` 10, `test_backfill_signal_embeddings.py` 4, `test_session_service.py` +3, `test_session_analysis.py` asserts the indicator; backend 726 unit and 237 integration pass; ruff, format and mypy clean)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (pipeline, embeddings), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `DEPLOYMENT.md` (the backfill command), `README.md` (the new make target) (also `.env.example`; DEPLOYMENT: new section "10. Backfilling signal embeddings", its `> Status:` line waits for the deploy; TESTS: every row compared with `--collect-only`)

**Commit checkpoint**
- [x] `feat: tag critical indicators and embed signals` (571c406; CI run 37982484979 green, backend deployed; ownership taken after 115 s, the old task's release logged; `make backfill-embeddings ENV=staging ARGS=--dry-run`: 0 signals to fill, exit 0)

### Phase 4: Recompute service, flags and jobs
**Code work**
- [x] `app/db/repositories/health_repo.py` (snapshots: add, latest per placement, history; flags: open ones, add, add evidence); `signal_repo` (a placement's signals up to a time; open issues with a Technical signal); `placement_repo` (active placements; `ListScope` filter on `_rows`) (also `latest_computed_at`, `signal_repo.latest_created_at`, `placement_repo.register_edits` and `active_ids_for_project` for the catch-up and hooks. Deviation: the `ListScope` filter on `_rows` moves to Phase 5, where the board first uses it)
- [x] `app/services/health_service.py`: `recompute(placement_id, reason)`: load, score, evaluate triggers, write the snapshot and open or extend flags in one transaction
- [x] Jobs: `health_recompute` per placement (dedups bursts), `health_daily` (fixed id) fanning out to every active placement, a daily loop to the next `HEALTH_DAILY_HOUR` in `HEALTH_TIMEZONE` started in `main.py` behind `HEALTH_DAILY_ENABLED`; runners registered before takeover (`app/services/health_jobs.py`; the reason rides on the queue job)
- [x] Hooks: after a session job that ends `completed` (embeddings, then the recompute; never after a failed analysis); after the register routes commit (placement create and edit, project edit fanning out to its active placements, import confirm when applied) (the import records the placements it created or whose fields changed; found on the way: the consultant, client and project edits answered 500, fixed in 632fc5d)
- [x] `processing_queue.py`: a key requested while its job runs is queued once more when it finishes (every kind)
- [x] Takeover requeue: placements whose newest signal or register edit is newer than their latest snapshot are recomputed, which also covers a daily job lost to a deploy across 06:00 (plus, per the user decisions 2026-10-10: every placement without a snapshot, and with the daily run on, every active placement not recomputed since the last scheduled run)
- [x] Tests: recompute against Postgres (snapshot, flags opened once, evidence added, not scored), jobs and fan-out, the queue re-run, hooks (enqueue after commit, only for completed sessions), the daily loop's next run across a clock change (no fixed sleeps) (unit: `test_health_jobs.py` 20, `test_processing_queue.py` 27 to 31; integration: `test_health_service.py` 10, `test_health_jobs.py` 9, `test_session_service.py` asserts the recompute hook; backend 750 unit and 259 integration, frontend 157 pass; ruff, format, mypy, eslint, tsc and Prettier clean)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (processing, health), `.env.example`, `DEPLOYMENT.md` (the daily recompute on staging), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (ARCHITECTURE: new section "Health recompute (as built)", `> Status:`; DEPLOYMENT: new section "11. Health recompute (daily run off until Phase 8)", its `> Status:` line waits for the deploy; also `API.md` (the register writes queue recomputes; the scan's `queued`); README: no new make target; TESTS: every row compared with `--collect-only`)

**Commit checkpoint**
- [x] `feat: recompute health after calls, edits and daily` (844aae6; CI run 38028603441 green, backend and frontend deployed; ownership taken after 150 s, the old task's release logged; the health catch-up logged nothing, since the staging register has no placements yet and a takeover step logs only when it handled a row; the fix deploy before it took ownership after 155 s)

### Phase 5: Board and placement health routes
**Code work**
- [x] Migration `007` and the recompute: `health_snapshots.technical_trend` and `technical_trend_delta`, from the Technical score a trend window back with the same flat band (user decision 2026-10-10: an SME's arrow must not reveal the overall's movement) (`007_add_snapshot_technical_trend.py`; `dimension_trend_between` in `scoring.py`, `HealthResult.technical_trend`)
- [x] `app/services/health_view.py`, `app/schemas/health.py`, `app/api/v1/placement_health.py` (tag `placement-health`; user decisions 2026-10-10 in the Decisions Log):
  - `GET /risk-board`: active placements in the caller's scope with the latest snapshot, open flags, weeks in, days since the last call, next action due; Technical only for an SME, sorted by Technical score then name, with no risk filter
  - `session_view.py`: an SME's session page lists only Technical signals (transcript, summary, issues and actions unchanged); an SME's sessions list counts only Technical signals
  - `GET /placements/{placement_id}/health` (logged placement scope): latest snapshot with evidence quotes, snapshot history, call markers, open flags with evidence, sessions, open issues, actions, register fields, the consultant's other placements in scope; Technical only for an SME
- [x] Tests: scope (404 outside, list filtered), SME responses without the hidden fields, the access log row, the coverage test (integration: `test_placement_health_api.py` 11, `test_sessions_api.py` +1, `test_health_service.py` +1, `test_health_schema.py` +1, `test_migrations.py` +1 for 007; unit: `test_health_scoring.py` +1; the coverage and session-scope tests walk the two new routes; backend 755 unit and 274 integration pass; ruff, format and mypy clean. Deviation: the page's register block is `register_fields`, since `register` shadows a `BaseModel` attribute; `sees_technical_only` in `entitlements.py`, `HealthView` in `enums.py`)
- [x] `processing_ownership._run_steps`: log every step's count, zero included (user decision 2026-10-10), with its test

**Doc updates (concurrent)**
- [x] `API.md`, `ARCHITECTURE.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (API: new section "Risk board and placement health", the SME note in Sessions; ARCHITECTURE: new section "Health views (as built)", migration 007, `> Status:`; TESTS: every row compared with `--collect-only`; README: no new make target; `.env.example`: no new setting; `DEPLOYMENT.md`'s status waits for the deploy that applies 007)

**Commit checkpoint**
- [x] `feat: add the risk board and placement health routes` (29ce60d); then `fix: hide contract fields from an SME's placement read` (the register read, user decision 2026-10-10)

### Phase 6: Risk board page
**Code work**
- [ ] `src/app/page.tsx` with `components/health/RiskBoard.tsx` (keeps the `h2` "Risk board"), `hooks/useHealth.ts` (30 s polling), `lib/health.ts`, `types/health.ts`; filters PS, tech lead, client, risk level; red first, then trend; "Not scored" last; the SME view; dark mode
- [ ] E2E seed (`seed_e2e_session.py --health`): dates relative to today, an indicator signal and a placement ending within 30 days, recomputed directly; `tests/e2e/risk-board.spec.ts`
- [ ] Tests: components (sorting, filters, the SME view), e2e

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (frontend), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the risk board`

### Phase 7: Placement health page
**Code work**
- [ ] `src/app/placements/[placementId]/page.tsx`, `components/health/{PlacementHealthView,DimensionScores,HealthChart,FlagList}.tsx` (Recharts through `components/ui/chart.tsx`, theme colours, call markers); links from the board, the sessions list and the session page; 404 shows "not found"
- [ ] Tests: components (SME view, not scored, chart data), e2e

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `ROADMAP.md` (tick the three Milestone 2 items)

**Commit checkpoint**
- [ ] `feat: add the placement health page`

### Phase 8: Staging rollout, exit gate, audit and handover
**Code work and setup**
- [ ] Deploy through CI; turn on the daily recompute on staging; run the embedding backfill; check the snapshots
- [ ] Exit gate: ten placements scored from real sessions; the PMO manager reviews the ranking; weight changes become a new configuration version

**Doc updates (concurrent)**
- [ ] `docs/tracking/SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-02-handover.md`, `BACKLOG.md`, `ROADMAP.md`

**Commit checkpoints**
- [ ] `docs: record the sprint 2 exit gate`
- [ ] `docs: complete sprint 2 audit and handover`

### Alongside: real calls on staging
- [ ] The user seeds the register on Admin > Register; the next scan matches the folders; settle any folder that names more than one consultant
- [ ] Calls processed from consultants who know their calls are analysed (who and when recorded here)
- [ ] Each run reviewed with the user (node errors, quotes rejected, cost, timing); fixes as their own `fix:` commits

## Blockers and Dependencies
- Real calls: the staging register (by hand, BACKLOG) and consultants told beforehand (BACKLOG #6); the exit gate needs ten scored placements.
- Phase 1's Terraform apply needs the user's approval; the fix waits for the evidence.

## Session State (last updated: 2026-10-10 10:00)
- **Sprint**: 2 — Health v1 (PRD Phase 2)
- **Current phase**: Phase 5 committed (29ce60d); Phase 6 (risk board page) not started (waits for the user)
- **Phase progress**: Phase 5: all tasks complete; the register read fix committed after it
- **Last completed task**: read both deploys' logs (2026-10-10, after the user's AWS sign-in): 632fc5d took processing ownership after 155 s, 844aae6 after 150 s, each with the old task's release logged; the 844aae6 takeover's health catch-up wrote no line because no placement exists on staging yet (a takeover step logs only a non-zero count; no WARNING, so it did not fail)
- **Next task**: push 29ce60d and the fix, read the deploy through to "Took processing ownership" (migration 007 applies) and update `DEPLOYMENT.md`'s status; then Phase 6 when the user asks
- **Last commit**: the register read fix after 29ce60d "feat: add the risk board and placement health routes" (not yet pushed)
- **Uncommitted changes**: none
- **Blockers**: none
- **Tests passing**: 755 unit + 275 integration (backend, run 2026-10-10 after the register read fix) + 157 frontend unit (run 2026-10-10) + 17 e2e (green in CI run 38027538149) = 1204
- **Files created this session**: `backend/alembic/versions/007_add_snapshot_technical_trend.py`, `backend/app/api/v1/placement_health.py`, `backend/app/schemas/health.py`, `backend/app/services/health_view.py`, `backend/tests/integration/test_placement_health_api.py`
- **Files modified this session**: (fix) `backend/app/api/v1/register.py`, `backend/app/schemas/register.py`, `backend/tests/integration/test_register_api.py`; (Phase 5) `backend/app/api/router.py`, `backend/app/db/repositories/{health,placement,session,signal}_repo.py`, `backend/app/health/scoring.py`, `backend/app/models/{enums,health}.py`, `backend/app/services/{health_service,processing_ownership,session_view}.py`, `backend/app/utils/entitlements.py`, tests `integration/{test_health_schema,test_health_service,test_migrations,test_sessions_api}.py` and `unit/{test_health_scoring,test_processing_ownership}.py`; docs `API.md`, `ARCHITECTURE.md`, `tracking/{CHANGELOG,FEATURES,TESTS}.md`, this file
- **Key decisions this session**: Phase 5: ten design decisions (Decisions Log, "Phase 5" rows), among them the Technical trend stored by migration 007, the SME view by role, server-side board order, one response model with `view`. Earlier, Phase 4: the catch-up covers a missed daily run and every placement without a snapshot; an applied import recomputes what it created or changed; "Scan now" during a scan answers `queued: true`; the register edit bug shipped as its own fix commit first; a takeover step logs a zero count (Phase 5); the Phase 3 and Phase 4 judgement calls approved (user decisions 2026-10-10, in the Decisions Log)
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-01-handover.md`.
  - **Local stack**: `docker compose up --build -d --wait`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS sign-in**: `aws sso login --profile pmo-intelligence`. Nothing is ever deleted or overwritten in the main ITC account (`430006376054`).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| The staging register is entered by hand on Admin > Register (consultant, client, project, placement), not imported from the PS team's CSV | Carried from Sprint 1 (user decision 2026-10-09, after that sprint closed); Process needs a placement covering the call. Alternatives offered: quick add from the Recordings tab; Process without a placement (both new features) |
| Every row of "User Decisions Made" above | User decisions 2026-10-09, Sprint 2 planning; alternatives listed with each |
| The backend target group drains for 60 s (was AWS's default 300 s) | User decision 2026-10-09, after the logs showed the drain was the whole takeover delay; an upload still running 60 s into a deploy's drain is cut and must be retried. Alternatives offered: 30 s; 120 s; keep 300 s |
| The backend container keeps the default `stopTimeout` (30 s) | User decision 2026-10-09; shutdown takes 0.1 s and the queue's grace is 10 s. Alternative offered: 60 s |
| Judgement calls made while building Phase 2, for approval at the checkpoint | An ended or terminated placement raises no new flags (it is still scored); the enumeration is `SignalIndicator`, not `Indicator`; `SnapshotReason` includes `catch_up` for the takeover's recompute (Phase 4), so no later CHECK change; a repeated blocker's "open more than 10 days" is strictly more than 10 × 24 hours since first seen; the downward-trend evidence is the negative signals said within the trend window |
| Phase 3: the backfill on staging runs as a one-off task from the backend's task definition, through `make backfill-embeddings ENV=<env>` | User decision 2026-10-10; the `admin-cli` task has only `DATABASE_URL`. Alternatives offered: give `admin-cli` the Azure OpenAI settings (Terraform); local only |
| Phase 3: a failed embedding call leaves the signals' embeddings NULL until the backfill command is run; no automatic catch-up | User decision 2026-10-10; nothing reads embeddings this sprint. Alternative offered: a takeover requeue step |
| Phase 3: one shared `ExtractedSignal.indicator` offering all three values; each prompt lists only its own indicators; emit clears an indicator its node may not set and keeps the signal | User decision 2026-10-10 (as planned). Alternative offered: a narrowed schema per node |
| Phase 4: the takeover catch-up also recomputes, when `HEALTH_DAILY_ENABLED` is on, every active placement whose latest snapshot is older than the most recent scheduled daily run (06:00 UK) | User decision 2026-10-10: the plan's rule (newest signal or register edit newer than the latest snapshot) misses a daily run lost to a deploy. Alternative offered: as written only |
| Phase 4: a placement with no snapshot yet is recomputed by the catch-up whatever its status (ended and terminated included) | User decision 2026-10-10; they are still scored and raise no new flags. Alternative offered: active only |
| Phase 4: an applied CSV import recomputes the placements it created or changed | User decision 2026-10-10. Alternatives offered: every placement in the file; every active placement |
| Phase 4: with the queue re-run, `POST /recordings/scan` answers `queued: true` when a scan is running (a second one is booked), `false` only when one is already waiting to start | User decision 2026-10-10. Alternative offered: keep `false` while one runs |
| Judgement calls made while building Phase 3 (approved by the user 2026-10-10) | Which extraction may set which indicator is one constant, `SIGNAL_INDICATORS_BY_CATEGORY` in `enums.py`, read by the prompts and emit; when two readings of one quote set different indicators, the first wins (relationship/engagement is read before client); cleared indicators are counted (`indicators_cleared`) and logged, not stored. The embedded text is the quote, then the note on its own line. Embedding settings `SIGNAL_EMBEDDING_BATCH_SIZE` (100 per request) and `SIGNAL_EMBEDDING_TIMEOUT_SECONDS` (120, for the whole session). A session's embeddings and cost rows are one commit, all or nothing; the cost row is service `azure_openai`, operation `signal_embeddings`, tokens in `input_tokens`, and the session page counts it as analysis. The embedding step runs after the job is marked completed (the job's `completed_at` is before it). The backfill goes session by session, oldest call first, with `--dry-run`, and exits 1 when any session fails; on a deployed environment its task runs the service's migration container first |
| Register edits of a consultant, client or project answer 500 today; fixed as its own `fix:` commit, pushed before the Phase 4 commit | User decision 2026-10-10. Found by Phase 4's project-edit hook test: no test had sent `PATCH` for those three routes, only for placements, whose response re-selects the row. Alternatives offered: push with Phase 4; fold into Phase 4 |
| **Audit note (Rule C, Sprint 2)** | The consultant, client and project `PATCH` routes shipped in Sprint 1 Phase 2 without a test that called them, and each answered 500 (an expired server-set `updated_at` read after the flush). Cause: route tests covered create, list and the placement edit, and the placement's response happened to re-select its row. Rule to add: every route gets at least one test that calls it through the client and reads the response it returns |
| Judgement calls made while building Phase 4 (approved by the user 2026-10-10) | The snapshot reason rides on the queue job (`Job.reason`, outside its identity, like the priority); a re-run takes the latest request's priority and reason. Calls and register writes recompute at session priority, the daily run and the catch-up at backlog priority. A recompute reads signals said within the lookback plus the trend window (104 days) and scores as of now; the level is decided after the flags. Snapshot evidence is `{dimension: {signal_count, contributors: [{signal_id, weight, value}]}}`, weights unrounded. The daily loop wakes at least hourly to re-read the clock. The catch-up's register edit is the later of the placement's and its project's `updated_at`, and a signal's time is when it was stored (`created_at`). Creating a project, or editing a consultant or client, queues nothing (no placement's health reads them); an import counts a placement as changed when its own fields changed |
| A takeover step logs its count even when it is zero ("Takeover re-queue health catch-up: 0 row(s)"), so "ran and found nothing" can be told from "never ran"; folded into Phase 5 | User decision 2026-10-10, after the 844aae6 deploy's catch-up left no line on a staging register with no placements (the Sprint 2 audit note's rule: when a step leaves no log line, add one). Alternative offered: leave it |
| Phase 5: an SME's Technical trend is stored on the snapshot (`technical_trend`, `technical_trend_delta`, migration 007), from the Technical score a trend window back, with the same flat band | User decision 2026-10-10; the stored trend is the overall's, so showing it to an SME would reveal the overall's movement. Alternatives offered: no trend for SMEs; compute on read |
| Phase 5: the Technical-only view follows the role (`users.role = sme`), not how a placement names the caller | User decision 2026-10-10; the role is the entitlement. Alternative offered: per placement, by how the caller is named |
| Phase 5: the server sorts the board: red, amber, green, then not scored (no snapshot counts as not scored); within a level trend down, flat, up, then none; then overall ascending; then consultant name | User decision 2026-10-10. Alternatives offered: level, overall, name; sort in the page. Judgement call, for approval at the checkpoint: an SME's board (planned "by Technical score, then name") sorts lowest Technical first, not scored last |
| Phase 5: the board's filters (PS, tech lead, client, risk level) run in the browser on fields the API returns | User decision 2026-10-10, as the sessions list. Alternative offered: query parameters |
| Phase 5: one response model per route with `view` (`full`, `technical`); for an SME, overall, level, trend, flags and the other five dimensions are null or empty | User decision 2026-10-10. Alternative offered: separate models |
| Phase 5: the placement page lists every action of the placement, open and overdue first by due date (undated last), then done ones, newest closed first | User decision 2026-10-10. Alternative offered: open and overdue only |
| Phase 5: an SME sees the register's dates, status and people (start, expected end, status, PS, SME, tech lead, client manager), not extension status, rate band or ended reason | User decision 2026-10-10. Alternative offered: every register field |
| Phase 5: the board's next action due is the open or overdue action with the earliest due date, past dates included; undated actions never show | User decision 2026-10-10. Alternative offered: fall back to the oldest undated action |
| Phase 5: the health history returns every snapshot, oldest first | User decision 2026-10-10. Alternative offered: last snapshot per UK day |
| Phase 5: "days since the last call" counts from the latest completed session's call, in UK days | As planned ("the last processed call") |
| Judgement calls made while building Phase 5 (approved by the user 2026-10-10 with the commit) | An SME's board sorts lowest Technical score first, not scored last, then name; `weeks_in` is 0 before the start; the page's register block is `register_fields` (`register` shadows a `BaseModel` attribute); the page's completed sessions are the chart's call markers (no separate list); `HealthView` lives in `enums.py` and `sees_technical_only` in `entitlements.py` |
| The register read `GET /placements/{placement_id}` gave an SME the extension status, rate band and ended reason the health page hides; fixed as its own `fix:` commit straight after the Phase 5 commit (it uses Phase 5's `sees_technical_only`), pushed with it | User decision 2026-10-10. Alternatives offered: fold into Phase 5; backlog it |
| **Audit note (Rule C)** | Sprint 1 recorded that the old task's log "ends without shutdown lines" and guessed the lock was freed by the dropped connection; the lines were there, and the delay was the documented 300 s drain (the ownership module's own docstring named it). Cause: a log was skimmed for a line that `release()` never wrote, and the conclusion went into the backlog untested. Rule to add: before recording a cause, find the log line or timestamp that shows it; when a step leaves no log line, add one rather than infer |
