# Sprint Audit Report

> **This file is a MANDATORY artifact.** It must be filled out BEFORE the handover document is created.

## Sprint: 02 (Health v1)
## Date: 2026-10-11

The Sprint 1 report is in git history (`957e497`, "docs: complete sprint 1 audit and handover") and summarised in `docs/handover/sprint-01-handover.md`.

**Status**: PASSED. The sprint closed without its exit gate (ten placements scored from real sessions and reviewed by the PMO manager), because the staging register is still empty and no real call has been processed; user decision 2026-10-11. The gate is in BACKLOG (High Priority), with Sprint 1's gate, which the same calls can serve.

---

## Verification Checklist

Check each item. Mark `[x]` only after actually verifying (not from memory).

### Test Counts
- [x] Backend tests verified by running test command → count matches TESTS.md (`uv run pytest -q -rf`: 1035 passed in 264 s, no failure; `pytest --collect-only`: 759 unit and 276 integration in 76 files; every one of the 76 backend rows of TESTS.md matches its file, the five names shared by the unit and integration folders included)
- [x] Frontend tests verified by running test command → count matches TESTS.md (`pnpm test -- --maxWorkers=4`: 35 files, 199 passed; `vitest list --json` per file matches every row; `playwright test --workers=1` against the rebuilt compose stack: 21 passed, and each spec's count matches its row)
- [x] Grand total matches (759 + 276 + 199 + 21 = 1255, as in TESTS.md)

### Lint
- [x] Linter passes with no errors (`make lint` exit 0: ruff check, ruff format check on 214 files, mypy strict on 123 source files; eslint, `tsc --noEmit`, Prettier check)

### Documentation Verification
- [x] CHANGELOG.md has entry for this sprint (`[Unreleased]`: every Sprint 2 deliverable under Changed, Fixed and Added, the daily recompute's Terraform variable included)
- [x] FEATURES.md has all new features logged (the "Sprint 2: Health v1" section has a row for each deliverable of the 10 code commits, operator features included: the drain, the backfill command, the takeover counts, the daily run's variable)
- [x] TESTS.md row counts match actual test output (all rows, above; its summary line now names this run)
- [x] BACKLOG.md completed items checked off (the takeover delay ticked in Phase 1; open questions 5 and 7 decided at planning; new: the Phase 2 exit gate and the still open Phase 1 gate in High Priority, the two `sessions.spec.ts` local failures in Tech Debt from Phase 6)
- [x] ROADMAP.md completed milestones checked off (Milestone 2's three items ticked in the phase commits that delivered them; its exit gate marked not run)
- [x] ARCHITECTURE.md reflects current state (backend, session pipeline, health model, recompute, views, frontend and infrastructure sections compared with the code; `config/v1.json` matches every stated value; status line moved to "Sprint 2 complete")
- [x] API.md accurately describes endpoints (40 live `/api/v1` routes from the app, 40 listed, none missing either way)
- [x] .env.example lists all env vars (63 `Settings` fields, 63 keys, none missing either way)
- [x] No tooling or authorship traces in any committed file (`git grep` of tracked files with the pre-commit hook's pattern and for the rules folder's path: none; no tool configuration file tracked; the 11 Sprint 2 commit messages are clean)
- [x] Git commits follow conventional commit format (11 commits since `957e497`: 7 `feat`, 3 `fix`, 1 `docs`, all listed types)
- [x] Dependency lists current (no package added or removed: `pyproject.toml`, `uv.lock`, `package.json` and `pnpm-lock.yaml` unchanged since `957e497`)

**File paths**: 995 backtick path references in README.md, ARCHITECTURE.md, API.md, DEPLOYMENT.md, TESTS.md, FEATURES.md, CHANGELOG.md, BACKLOG.md, ROADMAP.md, CURRENT-SPRINT.md, TEAMS-GRAPH-SETUP.md and the Sprint 1 handover were checked against the tracked files and folders (bare names against the folder their row names). All resolve except non-paths (a CIDR, a date format, a media type, a secret name, the repository name, an S3 prefix), the git-ignored `backend/.env` and `.terraform/`, and `docs/handover/sprint-02-handover.md`, written after this audit.

**Commands**: run during the audit or this sprint's last session: `make lint`, the suites above (`make test` and `make test-e2e` run their commands), `make migrate`, `make backfill-embeddings ENV=staging ARGS=--dry-run` (exit 0; finding S2-6), `terraform plan` and `apply` for staging. The README's command table has a row for the one make target added this sprint (`backfill-embeddings`). Every log line DEPLOYMENT.md and CHANGELOG.md quote was compared with the code's format strings (finding S2-8).

---

## Findings

Findings S2-1 to S2-7 were recorded in `docs/planning/CURRENT-SPRINT.md` (Decisions Log, "Audit note" rows) as they happened, and fixed then. S2-8 was found by this audit and fixed in it. Every finding has a local rule and a Learnings Log line.

| # | What was wrong | Root cause | Rule added/updated |
|---|---------------|-----------|-------------------|
| S2-1 | Sprint 1 recorded that the old task's log "ends without shutdown lines" and that the lock was freed by Postgres dropping the connection; the lines were there, and the 370–390 s takeover delay was the target group's default 300 s drain, which the ownership module's own docstring named | A log was skimmed for a line `release()` never wrote, and the guess went into the backlog untested | Infra and tooling: record a cause only with the log line or timestamp that shows it; where a step writes no log line, add one rather than infer |
| S2-2 | Editing a consultant, client or project on Admin > Register answered 500 since Sprint 1 Phase 2 (fixed in 632fc5d) | Route tests covered create, list and the placement edit, whose response happens to re-select its row; nothing called the other three `PATCH` routes | Testing: every route is called by a test through the client that reads its response |
| S2-3 | After the 844aae6 deploy the health catch-up left no log line, so a step that ran and found nothing could not be told from one that never ran | A takeover step logged only when it handled a row | Code style: every startup and takeover step logs its outcome, zero included (done in Phase 5) |
| S2-4 | The risk-board e2e saw a placement's two flags in either order | A recompute opens every flag at one `as_of`, so the open-flag query's tie on `opened_at` fell to a random UUID; the Sprint 1 tie-breaker rule was applied to signals but not checked on the new queries | Code style: when the first sort key is a time written in bulk, name a meaningful tie-breaker (severity, then the enumeration's order) before the id |
| S2-5 | The health chart's three RAG bands never rendered; no warning | Recharts 2.15 reads a chart's children with a `react-is` that predates React 19's element type and drops a Fragment. Caught only because the chart's unit test counted the reference areas | Testing: a chart's unit test renders the SVG and counts every kind of mark; code style: a Recharts chart's children are never a Fragment |
| S2-6 | `make backfill-embeddings` failed at once ("Error handling -chdir option") | `MSYS_NO_PATHCONV=1` was exported for the whole command; the script hands a POSIX path to Windows Terraform's `-chdir`, which works only through Git Bash's conversion, and it already sets the variable for its one `aws logs` call | Infra and tooling: set `MSYS_NO_PATHCONV=1` on the one command whose argument needs it, never exported |
| S2-7 | The 8b5b37c checkpoint was announced, and its sprint-file line committed, as running no CI job beyond Detect Changes; CI ran Backend CI, Frontend CI and E2E too (the deploy was skipped, as said) | Only the deploy filter in `ci.yml` was read; on `develop` the test filters compare with `main` | Git workflow: read both filters before saying what a push runs, and state the test jobs and the deploy apart |
| S2-8 | DEPLOYMENT.md, section 11, told operators to look for `Takeover requeue health catch-up: N row(s)`; the code logs `Takeover re-queue …`. Fixed in this audit | The line was written in Phase 4 from the function's docstring wording, not from the format string (`_run_steps("re-queue", …)`) | Sprint workflow: copy a quoted log line from the code's format string or a real log, never from memory |

---

## Audit Result
- [x] All checklist items verified
- [x] All findings fixed (S2-1 to S2-7 during the sprint, S2-8 in this audit); the exit gate moved to the backlog by the user
- [x] Every finding has a rule (9 rules for 8 findings: infra and tooling 2, testing 2, code style 3, git workflow 1, sprint workflow 1)
- [x] Learnings Log updated (8 lines)
- [x] **AUDIT COMPLETE** — **AUDIT PASSED** → handover document can be created
