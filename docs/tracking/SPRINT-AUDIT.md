# Sprint Audit Report

> **This file is a MANDATORY artifact.** It must be filled out BEFORE the handover document is created.

## Sprint: 01 (Register and Sessions)
## Date: 2026-10-09 (first pass, before the exit gate; to be re-checked after it)

The Sprint 0 report is in git history (`5434bec`, "docs: complete sprint 0 audit and handover") and summarised in `docs/handover/sprint-00-handover.md`.

**Status**: first pass complete. Every check below passed or its finding is fixed and has a rule. Still open before the audit can be marked passed: the exit-gate calls (Phase 6), and a second pass over anything they change.

---

## Verification Checklist

Check each item. Mark `[x]` only after actually verifying (not from memory).

### Test Counts
- [x] Backend tests verified by running test command → count matches TESTS.md (`uv run pytest tests/unit`: 624 passed; `uv run pytest tests/integration`: 201 passed; per-file counts from `pytest --collect-only` match all 46 unit and 19 integration rows)
- [x] Frontend tests verified by running test command → count matches TESTS.md (`vitest run --maxWorkers=4`: 30 files, 157 passed, per-file counts from the JSON report match every row; `make test-e2e` on the compose stack: 17 passed)
- [x] Grand total matches (624 + 201 + 157 + 17 = 999, as in TESTS.md)

### Lint
- [x] Linter passes with no errors (`make lint` exit 0: ruff check, ruff format check, mypy strict on `app`; eslint, `tsc --noEmit`, Prettier check)

### Documentation Verification
- [x] CHANGELOG.md has entry for this sprint (`[Unreleased]`: every Sprint 1 commit's deliverable, under Security, Fixed and Added)
- [x] FEATURES.md has all new features logged (Sprint 1 section; fixed during the sprint: finding S1-6)
- [x] TESTS.md row counts match actual test output (fixed: finding S1-9)
- [x] BACKLOG.md completed items checked off (questions 2 and 3 decided; the token, debug, AssemblyAI key and manual redeploy items ticked; new items: the takeover delay, the Vitest timeouts)
- [x] ROADMAP.md completed milestones checked off (Milestone 1: register, ingestion, pipeline and session page ticked; its exit gate is open)
- [x] ARCHITECTURE.md reflects current state (backend, session pipeline, frontend, local development, CI/CD and infrastructure sections match the files; status line to be moved to "Sprint 1 complete" with the handover)
- [x] API.md accurately describes endpoints (all 38 `/api/v1` routes of the live app are listed, and every listed route exists)
- [x] .env.example lists all env vars (every field of `Settings` is present, and nothing else)
- [x] No tooling or authorship traces in any committed file (`git grep` of tracked files against the pre-commit hook's pattern: none; no tool configuration files tracked; the 18 Sprint 1 commit messages are clean)
- [x] Git commits follow conventional commit format (18 commits since `5434bec`: 13 `feat`, 3 `fix`, 1 `ci`, 1 `docs`, all listed types)
- [x] Dependency lists current (no package added or removed this sprint; `pyproject.toml` changed only in mypy's ignore list)

**File paths**: 761 path references in README.md, ARCHITECTURE.md, API.md, DEPLOYMENT.md, TESTS.md, FEATURES.md, CHANGELOG.md, BACKLOG.md, ROADMAP.md, TEAMS-GRAPH-SETUP.md and the Sprint 0 handover were checked against the tracked files. All resolve except `backend/.env` and `infra/environments/staging/terraform.tfvars` (git-ignored files the reader creates) and the glob `src/**/*.test.ts(x)`.

---

## Findings

Findings S1-1 to S1-11 were recorded in `docs/planning/CURRENT-SPRINT.md` as they happened (or, S1-3, in its Research Findings) and were fixed then. S1-12 was found in Phase 5 and moved to the backlog by the user. S1-13 was found by this audit and fixed in it. Every finding has a local rule and a Learnings Log line.

| # | What was wrong | Root cause | Rule added/updated |
|---|---------------|-----------|-------------------|
| S1-1 | A read straight after a save sometimes missed the new row (flaky register e2e), and a failed commit would still have answered success | The request session copied from Interview Intelligence committed after the response, FastAPI's documented default for a yield dependency | Code style: check copied infrastructure code against the framework's behaviour; a committing yield dependency uses `scope="function"`, with a test over every route |
| S1-2 | Two register e2e steps failed at random | Test-side: the first import after a restart is slow, and back-to-back runs hit the import's 10/minute limit as one e2e user | Testing: a step that waits on a server job gets the cold-start allowance; read the backend log (429, 5xx) before changing a flaky test |
| S1-3 | The survey reported mis-decoded dashes (`U+FFFD`) in folder names, and a repair step was planned | The cp1252 Windows console rendered the AWS CLI's UTF-8 output; read with boto3, the keys hold real en dashes | Infra and tooling: read non-ASCII data with a UTF-8 reader, never from the console's rendering |
| S1-4 | Local uploads had never worked (500 on the first write) | The copied Dockerfile switched to a non-root user without creating and chowning the volume's mount point; unit and integration tests write to a temporary directory | Infra and tooling: create and chown every path a non-root container writes to; an e2e test writes through it |
| S1-5 | `make dev-build && make migrate && make test-e2e` sat for 27 minutes | `dev-build` runs compose attached and never returns | Infra and tooling: chain only commands that return; start the stack detached when later steps depend on it |
| S1-6 | FEATURES.md was missed by the first three Phase 3 commits | The doc list was re-read only for the docs the change obviously touched | Sprint workflow: walk the phase's doc list item by item before every commit |
| S1-7 | Every backend deploy waits about 6.5 minutes (370–390 s, three deploys) before the new task takes processing ownership | The old task's lock appears to be freed by Postgres dropping its connection, not by a clean release; the log calls the wait "normal during a deploy", so it went unnoticed until a deploy was watched to the end. Fix in BACKLOG (tech debt) | Infra and tooling: after a backend deploy, read the log through to "Took processing ownership" and record the wait |
| S1-8 | The session page never started polling after a Retry when it had first loaded a failed session | SWR schedules its refresh timer only when `refreshInterval` changes; a function answering 0 never set one. The interval's unit test passed; only the retry e2e showed it | Code style: an interval that can be 0 lives in state, set from `onSuccess` |
| S1-9 | TESTS.md said 28 tests for `test_db_session_scope.py`; there were 34 after Phase 3 | The file is parametrised by route, and its row was not recounted when routes were added in another file | Sprint workflow: recount every TESTS.md row against `--collect-only` and Vitest's report |
| S1-10 | A new session-page integration test failed about one full run in two | Two seeded signals had equal `occurred_at`, so their order fell back to random ids | Testing: seed distinct sort keys; code style: ordered queries break ties on a meaningful column (offset) before the id |
| S1-11 | An e2e run reported a fixed failure as still failing | It ran against the frontend image built before the change | Infra and tooling: rebuild the changed service before e2e |
| S1-12 | One or two dialog tests (`UsersTab`, `PlacementDialog`) pass Vitest's 5 s limit in full runs with the default worker count while the compose stack runs | CPU contention: about 0.8 s alone, all 157 pass with `--maxWorkers=4`. Fix in BACKLOG (user decision) | Testing: re-run a timed-out test alone and with `--maxWorkers=4` before treating it as a regression |
| S1-13 | One backend unit test failed once in the audit run (623 of 624) and could not be named or reproduced in eight more runs | The audit command kept only the run's last line. The likely cause, `test_recordings_periodic.py`'s fixed 0.18 s sleep expecting three ticks of a 0.05 s loop, was changed to wait for the ticks themselves | Testing: no fixed sleeps for async ticks; keep failure names (`-rf`, never cut a run to one line) |

---

## Audit Result
- [ ] All checklist items verified (first pass done; re-check after the exit gate)
- [x] All findings fixed or moved to the backlog by the user (S1-7, S1-12)
- [x] Every finding has a rule
- [x] Learnings Log updated (13 lines)
- [ ] **AUDIT PASSED** → handover document can be created (after the exit gate and the second pass)
