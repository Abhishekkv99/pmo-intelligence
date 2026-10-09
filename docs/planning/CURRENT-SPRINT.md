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
| Embeddings client (after the design review) | The `openai` package's `AsyncAzureOpenAI.embeddings.create` with the same endpoint, key and deployment: exact token usage for the cost row and no tokenizer download in the non-root container; the unused `build_embeddings()` is replaced | LangChain's `AzureOpenAIEmbeddings` with an estimated cost and the tokenizer baked into the image |

## Task Checklist

>>> CURRENT PHASE: Phase 1

### Phase 0: Plan
- [x] Plan approved (2026-10-09)
- [ ] Commit `docs: plan sprint 2` (this file, `BACKLOG.md` #5 and #7 and the register item, `ROADMAP.md`)

### Phase 1: Processing takeover delay
**Code work**
- [ ] Investigate (read-only): the last backend deploy's old task (`aws ecs describe-tasks`: stoppingAt, stoppedAt, stopCode) and its CloudWatch log at shutdown (uvicorn "Shutting down", "Waiting for application shutdown", "Processing queue stopped") against the new task's "Took processing ownership after Xs"; decide between the deregistration delay and the keepalive explanation
- [ ] Fix, agreed with the user against the evidence: backend target group `deregistration_delay` (`infra/modules/environment/alb.tf`); backend container `stopTimeout` (`ecs.tf`, at most 120 on Fargate) so the queue stop and the release finish before SIGKILL; INFO lines in `ProcessingOwnership.release()` and the lifespan shutdown; uvicorn `--timeout-graceful-shutdown` below `stopTimeout` if needed (`backend/Dockerfile`); correct the docstrings that cite 300 s and 30 s (`processing_ownership.py`, `processing_queue.py`, `main.py`). A shorter deregistration delay also cuts in-flight requests, uploads included (up to 500 MB through the backend), at a deploy: weigh it with the user before choosing the value
- [ ] Terraform plan, `git status --untracked-files=all infra/`, approval, apply; one redeploy read through to "Took processing ownership" with the wait recorded
- [ ] Tests: the release log line

**Doc updates (concurrent)**
- [ ] `DEPLOYMENT.md` (deploy timing, `> Status:`), `ARCHITECTURE.md` (infrastructure, `> Status:`), `BACKLOG.md` (tick), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `fix: hand over processing promptly on deploy`

### Phase 2: Health tables, enumerations, configuration, scoring and triggers
**Code work**
- [ ] `app/models/enums.py`: `Indicator` with `INDICATOR_MEANINGS`, `RiskLevel` (green, amber, red), `Trend` (up, flat, down), `RiskTrigger` (all eight PRD triggers; six evaluated now), `FlagSeverity` (medium, high, critical) and the trigger severities
- [ ] Migration `006` and `app/models/health.py`:
  - `health_snapshots`: placement, computed_at, the six dimension scores, overall, trend, trend delta, risk level (empty when not scored), scored, signal count, `weights_version`, reason (call, register, daily), `evidence` JSONB (per dimension: the top five signals with weight and value, and the count); index on (placement, computed_at)
  - `risk_flags`: placement, trigger, severity, subject key (not null, `''` when the trigger has no subject, since NULLs never clash in a unique index), opened_at, `evidence_signal_ids`, closed_at, closed_by_user_id, closing_note; one open flag per (placement, trigger, subject key) by a partial unique index. With no closing this sprint, an open critical flag keeps its placement at least amber until Phase 4
  - `signals.indicator` (nullable, checked); an HNSW index on `signals.embedding` (`vector_cosine_ops`, m 16, ef_construction 64)
- [ ] Model and migration declare the HNSW index identically (ops and `WITH` options), so `alembic check` stays clean; `EXPECTED_TABLES` and the meanings test cover the new tables and enumerations
- [ ] `app/health/` (pure, no database, `now` passed in): `config.py` (`HealthConfig`, `load_health_config`), `config/v1.json`, `scoring.py` (`score_placement`: dimension scores, onboarding weighting by days since start, overall, trend from the signals whose call is on or before now − 14 days, decayed as of then, RAG with the critical floor, contributors), `triggers.py` (`evaluate_triggers`); settings `HEALTH_CONFIG_VERSION`, `HEALTH_DAILY_ENABLED`, `HEALTH_DAILY_HOUR`, `HEALTH_TIMEZONE`
- [ ] Tests: exact scores for fixed signal sets (prior, decay, confidence, the onboarding window, weights scaled), not scored, trend bands, RAG and the critical floor, each trigger at its edges, configuration validation; migration 006 up and down; constraints

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (health model as built, migration 006, `> Status:`), `.env.example`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the health scoring module and its tables`

### Phase 3: Indicator tagging and signal embeddings
**Code work**
- [ ] `ExtractedSignal.indicator` (`app/ai/session/schemas.py`, not on `Evidence`, which issues share); `prompts/common.py` lists `INDICATOR_MEANINGS` for the client and relationship/engagement prompts; `drafts.py` and `emit.py` carry it, allowing `client_dissatisfaction` and `consultant_change_requested` from the client node and `intent_to_leave` from the relationship/engagement node, and keeping an indicator when the same-quote dedup drops its duplicate; `session_analysis.py` stores it
- [ ] `app/services/signal_embeddings.py`: embed a session's signals (quote and note) with `AsyncAzureOpenAI.embeddings.create` (replacing the unused `build_embeddings()`) after the analysis commit, only for a `completed` session, in its own try/except so a failure never fails the session; a `processing_costs` row from `usage.total_tokens`; `signal_repo` reads and writes; `app/cli/backfill_signal_embeddings.py` (NULL embeddings, batched); confirm the staging secret's `AZURE_EMBEDDING_DEPLOYMENT` and the Azure deployment
- [ ] Tests: prompts list the meanings, emit and analysis keep the indicator; embeddings with a mocked client (success, failure non-fatal, cost row); the backfill command

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (pipeline, embeddings), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`, `DEPLOYMENT.md` (the backfill command)

**Commit checkpoint**
- [ ] `feat: tag critical indicators and embed signals`

### Phase 4: Recompute service, flags and jobs
**Code work**
- [ ] `app/db/repositories/health_repo.py` (snapshots: add, latest per placement, history; flags: open ones, add, add evidence); `signal_repo` (a placement's signals up to a time; open issues with a Technical signal); `placement_repo` (active placements; `ListScope` filter on `_rows`)
- [ ] `app/services/health_service.py`: `recompute(placement_id, reason)`: load, score, evaluate triggers, write the snapshot and open or extend flags in one transaction
- [ ] Jobs: `health_recompute` per placement (dedups bursts), `health_daily` (fixed id) fanning out to every active placement, a daily loop to the next `HEALTH_DAILY_HOUR` in `HEALTH_TIMEZONE` started in `main.py` behind `HEALTH_DAILY_ENABLED`; runners registered before takeover
- [ ] Hooks: after a session job that ends `completed` (embeddings, then the recompute; never after a failed analysis); after the register routes commit (placement create and edit, project edit fanning out to its active placements, import confirm when applied)
- [ ] `processing_queue.py`: a key requested while its job runs is queued once more when it finishes (every kind)
- [ ] Takeover requeue: placements whose newest signal or register edit is newer than their latest snapshot are recomputed, which also covers a daily job lost to a deploy across 06:00
- [ ] Tests: recompute against Postgres (snapshot, flags opened once, evidence added, not scored), jobs and fan-out, the queue re-run, hooks (enqueue after commit, only for completed sessions), the daily loop's next run across a clock change (no fixed sleeps)

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (processing, health), `.env.example`, `DEPLOYMENT.md` (the daily recompute on staging), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: recompute health after calls, edits and daily`

### Phase 5: Board and placement health routes
**Code work**
- [ ] `app/services/health_view.py`, `app/schemas/health.py`, a routes module that does not clash with the `/health` probe:
  - `GET /risk-board`: active placements in the caller's scope with the latest snapshot, open flags, weeks in, days since the last call, next action due; Technical only for an SME, sorted by Technical score then name, with no risk filter
  - `session_view.py`: an SME's session page lists only Technical signals (transcript, summary, issues and actions unchanged)
  - `GET /placements/{placement_id}/health` (logged placement scope): latest snapshot with evidence quotes, snapshot history, call markers, open flags with evidence, sessions, open issues, actions, register fields, the consultant's other placements in scope; Technical only for an SME
- [ ] Tests: scope (404 outside, list filtered), SME responses without the hidden fields, the access log row, the coverage test

**Doc updates (concurrent)**
- [ ] `API.md`, `ARCHITECTURE.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the risk board and placement health routes`

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

## Session State (last updated: 2026-10-09 21:20)
- **Sprint**: 2 — Health v1 (PRD Phase 2)
- **Current phase**: Phase 0 (plan approved; the plan commit is next)
- **Last completed task**: Sprint 2 planning; plan written here, with the design review's four decisions (trend basis, SME leaks, queue re-run, embeddings client) and its smaller fixes folded into the phases
- **Next task**: commit `docs: plan sprint 2` on the user's approval; then Phase 1, the read-only investigation of the takeover delay
- **Last commit**: 957e497 "docs: complete sprint 1 audit and handover" (pushed; CI run 37940241628 green, nothing deployed)
- **Uncommitted changes**: this file (Sprint 2 plan), `BACKLOG.md` (#5, #7, the register item), `ROADMAP.md`
- **Blockers**: none
- **Tests passing**: 624 unit + 201 integration (backend) + 157 frontend unit + 17 e2e = 999 (Sprint 1 audit run, 2026-10-09)
- **Files modified this session**: `docs/planning/{CURRENT-SPRINT,BACKLOG,ROADMAP}.md`
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
