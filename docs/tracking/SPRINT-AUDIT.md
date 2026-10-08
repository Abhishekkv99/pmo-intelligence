# Sprint Audit Report

> **This file is a MANDATORY artifact.** It must be filled out BEFORE the handover document is created.

## Sprint: 00 (Bootstrap)
## Date: 2026-10-08

---

## Verification Checklist

Check each item. Mark `[x]` only after actually verifying (not from memory).

### Test Counts
- [x] Backend tests verified by running test command → count matches TESTS.md (`uv run pytest tests/unit`: 289 passed; `uv run pytest tests/integration`: 47 passed; per-file counts from `pytest --collect-only` match all 31 rows)
- [x] Frontend tests verified by running test command → count matches TESTS.md (`vitest run`: 17 files, 88 tests, per-file counts match all 17 rows; `make test-e2e` on the compose stack: 9 passed)
- [x] Grand total matches (289 + 47 + 88 + 9 = 433, as in TESTS.md)

### Lint
- [x] Linter passes with no errors (`make lint` exit 0: ruff check, ruff format check, mypy strict on `app`; eslint, `tsc --noEmit`, Prettier check; `terraform fmt -check` clean in every stack and the module)

### Documentation Verification
- [x] CHANGELOG.md has entry for this sprint (`[Unreleased]`, every Sprint 0 deliverable)
- [x] FEATURES.md has all new features logged (fixed: finding A3)
- [x] TESTS.md row counts match actual test output
- [x] BACKLOG.md completed items checked off (the NS delegation and AssemblyAI key are checked; the open Teams items are current; fixed: finding A4)
- [x] ROADMAP.md completed milestones checked off (fixed: finding A1)
- [x] ARCHITECTURE.md reflects current state (status line updated to Sprint 0 complete; backend, frontend, local dev, CI/CD and infrastructure sections match the files)
- [x] API.md accurately describes endpoints (all 9 routes from `app.routes` listed, with the sign-in refusals)
- [x] .env.example lists all env vars (every field of `Settings` is present; `ALLOWED_EXTENSIONS` is a documented, commented example)
- [x] No tooling or authorship traces in any committed file (`git grep` of tracked files against the pre-commit hook's pattern: none; no tool configuration files tracked; commit messages clean)
- [x] Git commits follow conventional commit format (three `ci:` commits were outside the listed types: finding A5)

**File paths**: 245 path references in README.md, ARCHITECTURE.md, API.md, DEPLOYMENT.md, TESTS.md, FEATURES.md, CHANGELOG.md, BACKLOG.md and TEAMS-GRAPH-SETUP.md were checked against the disk. All resolve except `backend/.env`, which the README tells the reader to create (git-ignored by design).

---

## Findings

Findings 1–15 were recorded in `docs/planning/CURRENT-SPRINT.md` as they happened and were fixed then. Findings A1–A6 were found by this audit and fixed in it. Every finding has a local rule and a Learnings Log line.

| # | What was wrong | Root cause | Rule added/updated |
|---|---------------|-----------|-------------------|
| 1 | CI used `astral-sh/setup-uv@v10`, a tag that does not exist; the first run failed at job setup | Assumed every action publishes a floating major tag | Git workflow: verify every `uses:` ref with `gh api .../git/ref/tags/<tag>` before pushing |
| 2 | Docs said docs-only pushes skip CI on `develop`; paths-filter compares a non-default-branch push with `main` | The comparison base was read for the deploy filter only | Sprint workflow: state the comparison base whenever a doc describes path-filtered behaviour |
| 3 | The e2e run failed while another project's dev servers held 8000/3000 | Fixed ports assumed free | Infra and tooling: check the ports before e2e; use `PMO_API_PORT`/`PMO_WEB_PORT` (configurable ports added) |
| 4 | A saved plan named `tfplan-zone` (state data) showed as untracked | The ignore rule matched only `tfplan` | Infra and tooling: name plans `tfplan*` (rule widened) and check `git status` after every plan |
| 5 | The first deploy failed at OIDC sign-in | The trust condition was copied without reading the repository's immutable OIDC subject | Security: read the OIDC subject customisation before writing a trust policy |
| 6 | `docker login` to ECR failed with the Windows credential store | A Windows credential-helper limitation | Infra and tooling: use a temporary `DOCKER_CONFIG` for ECR |
| 7 | `make db-bootstrap` failed on Windows | make passed a script path containing a space unquoted | Infra and tooling: Makefile targets call scripts through `bash` |
| 8 | The Azure apply was blocked twice (MFA claim, then the resource-group policy) | The subscription's write requirements and policies were not read before planning | Infra and tooling: list policy assignments and test the MFA claim before an Azure plan |
| 9 | `az policy exemption create --scope /subscriptions/...` failed with MissingSubscription | Git Bash rewrote the leading `/` into a Windows path | Infra and tooling: `MSYS_NO_PATHCONV=1` for any argument starting with `/` |
| 10 | The Session State block named a stale last commit and work already done | It was written before the commit and apply it described | Sprint workflow: refresh Session State after each commit, push and apply |
| 11 | The first staging sign-in failed: the hand-pushed frontend image called `C:/Program Files/Git/api/v1` | Git Bash rewrote the `/api/v1` build argument; rule 9 was learned after the image was pushed; the health check passes without the API URL | Infra and tooling: grep a hand-built image's bundle for the API URL; re-check earlier manual steps when a rule is learned |
| 12 | The second sign-in hit "Need admin approval" | "Assignment required" was offered without stating that it forces admin consent; a follow-up wrongly said it could not cause the screen | Security: read Microsoft's page and state sign-in and consent side effects before offering an identity setting |
| 13 | The SSO script's re-run matched two apps and failed (no change made) | Windows PowerShell 5.1 `ConvertFrom-Json` pipes an array as one object; the script had been run only on the empty case | Infra and tooling: run idempotent scripts twice; wrap `ConvertFrom-Json` in parentheses |
| 14 | The admin task echoed every SQL statement | `app_debug` defaults to true and the task copied the migration container's environment, which has the same gap (backlogged) | Infra and tooling: every backend container sets `APP_DEBUG=false` outside development |
| 15 | A commit was blocked by the pre-commit hook | A committed line named the local rules' folder | Git workflow: committed docs say "local rules", never their path |
| A1 | ROADMAP Milestone 0 unchecked although delivered | Roadmap ticks were left for sprint end | Sprint workflow: tick ROADMAP items in the phase commit that delivers them |
| A2 | DEPLOYMENT.md status said "Phase 4 in progress" with 2026-10-07 resource counts | Status lines were not in each phase's doc list | Sprint workflow: update the `> Status:` lines in each phase commit; counts from `terraform state list` |
| A3 | FEATURES.md had no rows for Phases 3–5 (local stack, CI, infrastructure, database bootstrap, Azure OpenAI, reminders, SSO app) | FEATURES.md was treated as product features only and left out of the Phase 3 and 4 doc lists | Sprint workflow: FEATURES.md covers operator features and is in every phase's doc list |
| A4 | BACKLOG pointed to a "section 5" of TEAMS-GRAPH-SETUP.md that does not exist | A section was referenced by number without opening the doc | Sprint workflow: refer to sections by heading, after checking it exists |
| A5 | Three commits (`7329643`, `5e2a851`, `164e95a`) used `ci:`, outside the listed types | The type list was not checked before committing | Git workflow: `ci` added to the types for workflow-only changes; check the type before committing; never rewrite `develop` |
| A6 | The README command table lacked `make db-bootstrap` and `make user-role` | Targets were added with their DEPLOYMENT.md sections only | Sprint workflow: a new make target gets a README row in the same commit |

---

## Rules Added This Sprint

- **Git workflow** (local rules): commit types now include `ci`; check the type before committing; committed docs never name the local rules' path; verify every workflow `uses:` ref
- **Sprint workflow** (local rules): Session State after the action; ROADMAP ticks with the phase; status lines in every phase's doc list with counts from state; FEATURES.md covers operator features; cross-doc references by heading; README row for every new make target; state the comparison base for path-filtered CI
- **Security** (local rules): read the OIDC subject before a trust policy; state sign-in and consent side effects of identity settings; sign-in stays members-with-a-role (guests refused fail-closed, no row at sign-in, role re-checked on refresh and every request)
- **Infra and tooling** (new local rule file): free ports before e2e; `tfplan*` naming and `git status` after plans; plan approval before apply; `MSYS_NO_PATHCONV`; scripts through `bash`; ECR login through a temporary `DOCKER_CONFIG`; grep hand-built bundles; re-check old manual steps after a new rule; `APP_DEBUG=false` on backend containers; Azure policies and MFA before a plan; PowerShell re-runs and `ConvertFrom-Json` parentheses

---

## Audit Status

- [x] All checklist items verified
- [x] All findings fixed (one follow-up is in BACKLOG Tech Debt: `APP_DEBUG=false` on the migration container, which needs a backend redeploy)
- [x] All findings have corresponding rules
- [x] Learnings Log in the project instructions file updated (21 lines)
- [x] **AUDIT COMPLETE** — handover document may now be created
