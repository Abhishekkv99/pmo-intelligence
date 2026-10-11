# Sprint 02 Handover Document

**Sprint Duration**: 2026-10-09 - 2026-10-11 (planned 2026-10-12 – 2026-10-23; built and closed early)
**Sprint Objective**: PRD Phase 2 (Health v1). Turn signals into a deterministic health reading per placement: signal embeddings, the scoring module, health snapshots, triggers and risk flags, the daily recompute, the risk board and the placement (consultant) page; plus the processing takeover delay after backend deploys (BACKLOG tech debt).
**Audit Status**: PASSED — see `docs/tracking/SPRINT-AUDIT.md`

> **GATE**: This handover can ONLY be created AFTER the sprint audit is complete.

**Exit gate (PRD Phase 2): not run.** The gate is ten placements scored from their real sessions, with the PMO manager agreeing with the ranking or the weights tuned until they do. The staging register is still empty and no real call has been processed, so nothing on staging has been scored. The sprint closed without the gate (user decision 2026-10-11). Everything the gate needs is built and deployed, and the daily recompute is on in staging. The gate is in BACKLOG, High Priority, beside Sprint 1's gate, which the same calls can serve. ROADMAP Milestone 2 keeps its exit gate unticked.

## 1. What Was Achieved
- **Processing takeover after a deploy** (Phase 1): the old task already shut down cleanly in 0.1 s; the delay was the target group's default 300 s drain. The backend target group now drains for 60 s (`infra/modules/environment/alb.tf`), and `ProcessingOwnership.release()` logs "Released processing ownership" (`backend/app/services/processing_ownership.py`). Deploys since took ownership after 105–155 s (was 370–390 s).
- **Health model, pure** (Phase 2): `backend/app/health/` holds the versioned configuration (`config.py`, `config/v1.json`, chosen by `HEALTH_CONFIG_VERSION`), the scoring (`scoring.py`: six decayed dimension scores with a prior, overall, the 14-day trend and the Technical trend, RAG with the critical floor, top contributors) and six triggers (`triggers.py`). The enumerations are in `backend/app/models/enums.py`.
- **Tables** (Phases 2 and 5): migration 006 (`health_snapshots`, `risk_flags`, `signals.indicator`, an HNSW index on `signals.embedding`) and 007 (`health_snapshots.technical_trend` and its delta); models in `backend/app/models/health.py`. Both applied on staging.
- **Critical indicators and embeddings** (Phase 3): the client and relationship/engagement nodes tag `client_dissatisfaction`, `consultant_change_requested` and `intent_to_leave` when the quote says so (`backend/app/ai/session/`); a completed session's signals are embedded with text-embedding-3-small, costed and never failing the session (`backend/app/services/signal_embeddings.py`); `make backfill-embeddings ENV=<env>` fills any left empty (`backend/app/cli/backfill_signal_embeddings.py`, `scripts/backfill-embeddings.sh`).
- **Health recompute** (Phase 4): `backend/app/services/health_service.py` stores a snapshot and opens or extends flags in one commit; `backend/app/services/health_jobs.py` queues it after every analysed call, register write and applied import, daily at 06:00 UK, and at takeover for any placement out of date. The processing queue runs a job asked for during its run once more (`backend/app/services/processing_queue.py`).
- **Health views** (Phase 5): `GET /risk-board` and `GET /placements/{placement_id}/health` (`backend/app/api/v1/placement_health.py`, `backend/app/services/health_view.py`, `backend/app/schemas/health.py`), with the SME technical view, the server's board order, the logged placement scope and the RAG thresholds.
- **Risk board page** (Phase 6): `frontend/src/app/page.tsx` with `frontend/src/components/health/RiskBoard.tsx`, filters for PS, tech lead, client and risk level, RAG theme tokens in `globals.css`, 30 s polling.
- **Placement health page** (Phase 7): `frontend/src/app/placements/[placementId]/page.tsx` with `PlacementHealthView`, `DimensionScores`, `HealthChart` (Recharts: the overall over time, RAG bands, call markers), `FlagList` and `EvidenceItem`; linked from the board, the sessions list and the session page.
- **Staging rollout** (Phase 8): the Terraform variable `health_daily_enabled` sets `HEALTH_DAILY_ENABLED` on the backend container, true for staging, applied 2026-10-11 (task definition revision 4); the first daily run is 2026-10-12 06:00 UK. The embedding backfill dry run found nothing to fill.
- **Fixes**: consultant, client and project edits answered 500 (632fc5d); an SME's placement read by id hid no contract fields (2ec8369); open flags opened together came back in a random order (Phase 6).
- **Tests**: 1255 in all (759 backend unit, 276 integration, 199 frontend unit, 21 e2e), up from 999; per file in `docs/tracking/TESTS.md`.

## 2. What Was NOT Achieved
- **The Phase 2 exit gate**: no placement on staging is scored, since the register is empty and no real call was processed. Moved to BACKLOG, High Priority (user decision 2026-10-11).
- **Real calls on staging** (planned alongside the build): none processed or reviewed. Part of the exit gate item in BACKLOG; seeding the register is BACKLOG, Medium Priority.
- **Gone quiet and missed commitment triggers**: in `RiskTrigger` already, deferred to PRD Phase 3 (Teams chat) at planning, as they need the chat cadence and an action owner's updates.
- **Flag closing with a note**: deferred to PRD Phase 4 at planning; flags only open this sprint.

## 3. Decisions Made
Every decision with its alternatives is in the Decisions Log of `docs/planning/CURRENT-SPRINT.md` (this sprint's plan, in git history after the next sprint's plan replaces it). The ones that shape later work:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Score = decayed average with a prior: (P·7.0 + Σ wᵢvᵢ) / (P + Σ wᵢ), wᵢ = confidence × 0.5^(age/14 d), P = 1 | One signal moves a score without pinning it; the same evidence always gives the same number | Plain decayed average; baseline plus points |
| Weights and thresholds are the PRD's values as configuration file `v1`; a change is a new file, recorded on each snapshot | The exit gate tunes them; old snapshots stay explainable | Environment settings; a database table with an admin page |
| No signal in the 90-day lookback is "Not scored", listed last | A placement with no evidence is not green | The prior (7.0, green) |
| Trend from the signals whose call was on or before now − 14 days, decayed as of then | A backlog processed today still shows its trend | By when the signal was stored; a stored snapshot |
| Critical triggers read `signals.indicator`, set by two nodes with the quote as evidence | A critical flag needs explicit words, not a score threshold | Inferred from dimension and severity |
| An SME sees only the Technical score, its own stored trend and Technical evidence; their board sorts by Technical score | BACKLOG question 5; the order and trend must not reveal the overall | Same view as PS and tech lead; no health at all |
| Recompute after every call, register write and import, daily at 06:00 UK and at takeover, as queue jobs; a job asked for during its run runs again | The board reads a stored row; no edit is lost | Call and daily only |
| The placement page is per placement (`/placements/{id}`), logged; its thresholds come from the API | The placement is the unit of health; no constant in the page can drift from the configuration | Per consultant; thresholds mirrored in the frontend |
| The backend target group drains for 60 s | The drain was the whole takeover delay; an upload still running 60 s into a deploy's drain is cut | 30 s; 120 s; keep 300 s |
| The daily recompute is on in staging through the Terraform variable `health_daily_enabled` | One switch per environment, like the recordings scan | Not applying |
| Close Sprint 2 without the exit gate | No real data on staging yet | Seed the register first; wait for real calls |

## 4. Files Created / Modified
| File | Action | Description |
|------|--------|-------------|
| `backend/app/health/{__init__,config,scoring,triggers}.py`, `backend/app/health/config/v1.json` | Created | The pure health model and its v1 configuration |
| `backend/app/models/health.py`, `backend/alembic/versions/006_create_health_snapshots_and_risk_flags.py`, `007_add_snapshot_technical_trend.py` | Created | Snapshots, flags, indicator, embedding index, Technical trend |
| `backend/app/models/{enums,signal,__init__}.py` | Modified | Health enumerations and meanings; `signals.indicator` |
| `backend/app/services/{health_service,health_jobs,health_view,signal_embeddings}.py`, `backend/app/db/repositories/health_repo.py` | Created | Recompute, its jobs, the views, embeddings |
| `backend/app/api/v1/placement_health.py`, `backend/app/schemas/health.py` | Created | Risk board and placement health routes |
| `backend/app/cli/backfill_signal_embeddings.py`, `scripts/backfill-embeddings.sh` | Created | Embedding backfill and its one-off ECS task |
| `backend/app/ai/session/{drafts,emit,schemas}.py`, `prompts/{common,client_signals,relationship_engagement}.py`, `backend/app/ai/llm_factory.py` | Modified | Indicator tagging; the embeddings client |
| `backend/app/services/{processing_queue,processing_ownership,session_service,session_analysis,session_view,register_service,register_import}.py`, `backend/app/services/recordings/periodic.py`, `backend/app/main.py`, `backend/app/config.py` | Modified | Re-run, release and zero-count logs, recompute hooks, SME session view, settings, the daily loop |
| `backend/app/db/repositories/{placement,session,signal}_repo.py`, `backend/app/api/{router.py,v1/register.py,v1/recordings.py}`, `backend/app/schemas/register.py`, `backend/app/utils/entitlements.py`, `backend/app/cli/seed_e2e_session.py` | Modified | Queries, register hooks, the SME read, `sees_technical_only`, the `--health` seed |
| `backend/tests/unit/` (11 test files and 2 helpers, new or changed), `backend/tests/integration/` (12) | Created/Modified | 135 new unit and 75 new integration tests |
| `frontend/src/app/placements/[placementId]/page.tsx`, `frontend/src/components/health/` (7 components, 3 test files), `frontend/src/hooks/useHealth{,.test}.ts`, `frontend/src/lib/health{,.test}.ts`, `frontend/src/types/health.ts` | Created | Risk board and placement health page |
| `frontend/src/app/{page.tsx,globals.css}`, `frontend/src/components/{common/DataTable,sessions/SessionsList,sessions/SessionView,admin/recordings/RecordingsTab}.tsx` and their tests, `frontend/src/lib/constants.ts` | Modified | The board as home, RAG tokens, `sortable`, links to the placement page, "Scan now" wording |
| `frontend/tests/e2e/{risk-board,placement-health}.spec.ts` | Created | E2E for the board and the page |
| `infra/modules/environment/{alb,ecs,variables}.tf`, `infra/environments/staging/main.tf` | Modified | 60 s drain; `health_daily_enabled` |
| `Makefile`, `README.md`, `.env.example` | Modified | `backfill-embeddings` target and row; the new settings |
| `docs/{ARCHITECTURE,API,DEPLOYMENT}.md`, `docs/planning/{BACKLOG,ROADMAP,CURRENT-SPRINT}.md`, `docs/tracking/{CHANGELOG,FEATURES,TESTS,SPRINT-AUDIT}.md`, `docs/handover/sprint-02-handover.md` | Modified/Created | Kept current phase by phase; the audit and this handover |

## 5. Environment Changes
- **New dependencies**: none (`pyproject.toml`, `uv.lock`, `package.json` and `pnpm-lock.yaml` unchanged).
- **New environment variables**: `SIGNAL_EMBEDDING_BATCH_SIZE` (100), `SIGNAL_EMBEDDING_TIMEOUT_SECONDS` (120), `HEALTH_CONFIG_VERSION` (`v1`), `HEALTH_DAILY_ENABLED` (false; true in staging), `HEALTH_DAILY_HOUR` (6), `HEALTH_TIMEZONE` (Europe/London). All in `.env.example`.
- **Configuration changes**: the health configuration file `backend/app/health/config/v1.json`, shipped in the image.
- **Infrastructure changes**: the backend target group's deregistration delay is 60 s (applied 2026-10-09); the module variable `health_daily_enabled` puts `HEALTH_DAILY_ENABLED` on the backend container, true in staging (applied 2026-10-11, task definition revision 4). Staging still has 61 managed resources. Migrations 006 and 007 applied on staging by the CI deploys. Stale plan files deleted from `infra/environments/staging/`.

## 6. Known Issues / Bugs
- **Nothing is scored on staging yet** (high for the product, not a defect): the register is empty, so the board is empty. See Priority 1.
- **Nothing sets an action's `overdue` status** (low): the board and the page mark an action overdue from its due date against today's UK date, but the stored status stays `open`. Missed commitment (PRD Phase 3) will need the status or the same rule.
- **Embeddings are written but nothing reads them** (low): "who else had this blocker" search is later.
- **Two `sessions.spec.ts` e2e tests fail locally with Playwright's default workers** (low, BACKLOG Tech Debt): never in CI's single worker; causes recorded there.
- **Vitest dialog tests can pass the 5 s timeout under load** (low, BACKLOG Tech Debt): all pass with `--maxWorkers=4`.
- **The sidebar highlights no item on a placement page** (cosmetic): no navigation item owns `/placements`.
- **The backend tests do not pass mypy strict** (low, BACKLOG Tech Debt).

## 7. Learnings
### What Went Well
- The scoring module is pure and was tested with hand-worked numbers (43 scoring, 29 trigger, 15 configuration tests), so every later phase built on exact values.
- Reading every deploy through to "Took processing ownership" turned a long-standing guess into a measured fix (375 s to 105–155 s).
- Chart and view decisions were settled with the user before building, and the judgement calls made while building were listed for approval at each checkpoint.

### What Didn't Go Well
- The sprint was built ahead of the data it needs: the staging register was never seeded, so no real call was processed and the exit gate could not run, for the second sprint in a row.
- Three findings were statements made from memory: a cause recorded without its log line (S2-1), what a push runs (S2-7), and a quoted log line (S2-8).
- A copied rule was applied too broadly: `MSYS_NO_PATHCONV=1` exported for a script that relies on path conversion (S2-6).

### Rules Added / Updated
Nine local rules, one or more per finding: infra and tooling (a cause only with its evidence; the path conversion switch on one command), testing (every route called and its response read; chart tests count their marks), code style (steps log zero counts; a named tie-breaker for bulk-written times; no Fragment among chart children), git workflow (read both CI filters), sprint workflow (copy a quoted log line from its source). Eight Learnings Log lines.

## 8. Post-Sprint Audit Findings
**Findings count**: 8
**Rules added**: 9

| What was wrong | Root cause | Rule added/updated |
|---------------|-----------|-------------------|
| S2-1: Sprint 1 blamed the takeover delay on a dropped connection; it was the 300 s drain, and the shutdown lines were in the log | A log was skimmed for a line `release()` never wrote | Record a cause only with its log line or timestamp; add a log line where a step leaves none |
| S2-2: Consultant, client and project edits answered 500 since Sprint 1 | No test called those three `PATCH` routes | Every route is called by a test that reads its response |
| S2-3: The health catch-up left no line when it found nothing | Takeover steps logged only when they handled a row | Every startup and takeover step logs its count, zero included |
| S2-4: Two flags opened together came back in either order | A bulk-written `opened_at` tie fell to a random id | Name a meaningful tie-breaker after a bulk-written time |
| S2-5: The chart's RAG bands never rendered | Recharts 2 drops a Fragment child under React 19 | Chart tests count every mark; no Fragment among chart children |
| S2-6: The embedding backfill failed at once | `MSYS_NO_PATHCONV=1` exported around a script that needs path conversion | Set it on the one command that needs it |
| S2-7: A push was said to run only Detect Changes; it ran every test job | Only the deploy filter was read | Read both CI filters and state them apart |
| S2-8: The deploy doc quoted `Takeover requeue` for `Takeover re-queue` | Written from memory, not from the format string | Copy a quoted log line from the code or a real log |

## 9. Next Sprint Recommendations
### Priority 1 (Must Do)
- **Run the exit gates on staging before PRD Phase 3 is built**: seed the register on Admin > Register for the consultants whose calls are wanted (a placement whose dates cover the calls), settle any folder that names more than one consultant, process calls from consultants told beforehand (BACKLOG question 6), and review each run (node errors, rejected quotes, cost, timing). Then Sprint 1's gate (three calls, signals and summary agreed) and Sprint 2's (ten placements scored, the ranking agreed or the weights tuned as `v2.json`). The PRD makes each phase's staging sign-off the start of the next.
- **Confirm the chat RSC state with a Teams admin and run step A5** of `docs/integrations/TEAMS-GRAPH-SETUP.md` (BACKLOG High Priority), since PRD Phase 3 cannot start without it.

### Priority 2 (Should Do)
- **Plan PRD Phase 3 (Teams chat)**: the Graph connector and poller, the message store, the chat pipeline and cadence, messages on the placement page, and the gone-quiet and missed-commitment triggers (which also settles the `overdue` status).
- Narrow the Teams app's availability to the PMO team (BACKLOG High Priority, an admin action).

### Priority 3 (Nice to Have)
- BACKLOG Tech Debt: the two local `sessions.spec.ts` failures, the Vitest dialog timeouts, mypy strict on the backend tests.
- Highlight a navigation item on the placement page.
