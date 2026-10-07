# Sprint 0: Bootstrap

**Status**: `in-progress`
**Duration**: 2026-10-07 – 2026-10-20 (2 weeks)
**Objective**: Bootstrap the repository: the stack copied from Interview Intelligence (queue, ownership lock, LLM factory, auth, CI, Docker, Terraform), SSO sign-in with roles, an empty dashboard deployed to staging, the Graph app registration created and the Teams permission request submitted.
**Exit gate** (PRD Phase 0): the staging URL signs in with SSO; CI is green on `develop`; the Teams permission request has a ticket number.
**Source repo**: `E:\E Projects\Interview Intelligence Platform` (develop @ 51e617b)
**Branch**: all Sprint 0 work on `develop`; `main` stays at the docs commits until the first release.

---

## Research Findings Summary
- **Teams Graph access (2026-10-06)**: full detail and sources in `docs/integrations/TEAMS-GRAPH-SETUP.md`.
  - Teams APIs have not been metered since 2025-08-25.
  - The least-privileged app permission for reading chat messages is RSC `ChatMessage.Read.Chat`. Chat RSC defaults to `ManagedByMicrosoft`.
  - Whether `Chat.Read.All` still needs protected-API approval is unconfirmed.
  - Polling limits: `$top` max 50; `$filter` on `lastModifiedDateTime` needs a matching `$orderby`.
- **GitHub**: branch protection and rulesets on private repos need GitHub Pro.
- **Next.js**: 16.0.0–16.2.10 are affected by a middleware/proxy auth bypass (CVE-2026-64642) and eight other CVEs, fixed in 16.2.11 (2026-07-21). Interview Intelligence is on 16.1.6, so PMO upgrades to the latest 16.x at copy time.
- **Terraform**: the S3 backend supports native state locking (`use_lockfile = true`). DynamoDB locking is deprecated. Bucket versioning is recommended.
- **Interview Intelligence hazards** (from exploring the repo):
  - **Local state**: `infra/` holds a live local `terraform.tfstate`, `terraform.tfvars` and `.terraform/`. Copy only `*.tf` and `terraform.tfvars.example`.
  - **OIDC provider**: the GitHub OIDC provider already exists in the account, so use a data source.
  - **Drift**: the ALBs and RDS were changed by hand. Look up shared resources live.
  - **Shared ALB**: II's `/api/*` ALB rule has no host condition (priority 1), so sharing its ALB would route PMO's API to II.
  - **No SQL path to RDS**: there is no ECS exec and RDS is private.
  - **Coupling**: the queue, ownership lock, sweeps, `dependencies.py`, entitlements, processing models and integration conftest are coupled to interview and ingestion code.
  - **mypy**: configured strict, but never run in CI.
  - **Deploy**: the build-push workflow deploys even when CI fails.
  - **Broken targets**: `make format` and `make seed` are broken.

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|
| Environments and database (#8) | Staging + prod. **Revised 2026-10-07: fully separate infrastructure from Interview Intelligence**: own VPC, VPC endpoints and RDS instance (was: own databases on II's shared RDS instance) | Staging only; own databases on the shared RDS instance; own RDS instance in the shared default VPC |
| UK only or UK + US (#9) | UK only, no branch column | Model branch from day one |
| Hostnames (#10) | `pmo-intelligence.itcapp.ai` (prod), `pmo-intelligence-staging.itcapp.ai` (staging) | `pmo.itcapp.ai` is taken; `placements.itcapp.ai`; `pmo-intel.itcapp.ai` |
| Load balancer | Two new ALBs (staging and prod), as in Interview Intelligence | One new ALB for both; share II's ALB |
| Terraform state | S3 remote backend with native locking | Local state like II |
| SSO credential | Client secret, with its expiry recorded and reminded | Certificate credential |
| Sprint length | 2 weeks | 1 week; until the exit gate |
| Frontend package manager | pnpm (as in II) | npm |

## Task Checklist

### Phase 1: Backend skeleton
**Code work**
- [x] Copy the generic backend files as-is (pyproject/uv.lock, alembic env, db session and base repository, user and refresh-token models, LLM factory, cost tracker, exceptions, memory, security middleware, rate limiter, auth routes and services, health and processing-status routes)
- [x] Rewrite `processing_queue.py` (generic core with an injected runner registry) and `processing_ownership.py` (injectable sweeps)
- [x] Rewrite `dependencies.py`, `main.py` (lifespan: bootstrap admins, then `hold_processing`), `config.py` (PMO names) and `api/router.py`
- [x] Role model: nullable `users.role` (`pmo_manager | sme | tech_lead | ps | admin`); bootstrap admins raised to `pmo_manager`; new SSO users get no role
- [x] Scope foundation: `Principal`, `require_placement_scope` (404 plus a WARNING), `access_log` writer, route-coverage test
- [x] Migration 001: vector extension plus users, refresh_tokens, consultants, clients, projects, placements, processing_jobs, processing_costs, access_log
- [x] Prune dependencies (drop the unused second LLM SDK and the report/teams-matching libraries: fpdf2, weasyprint, rapidfuzz, markdown, xlsxwriter) and run `uv lock`
- [x] Tests: adapt both conftests and the kept II tests; add entitlement, coverage, access-log and migration smoke tests; mypy strict passes

**Doc updates (concurrent)**
- [x] `docs/ARCHITECTURE.md`: backend layout, role model, migration 001 as built
- [x] `docs/API.md`: health, auth, processing-status endpoints
- [x] `docs/tracking/TESTS.md`, `FEATURES.md`, `CHANGELOG.md`

**Commit checkpoint**
- [x] `feat: add backend skeleton with auth, role scope and migration 001` (5969dda; 274 tests, ruff and mypy green; tool-reference scan clean)

### Phase 2: Frontend skeleton
**Code work**
- [x] Copy the frontend (without `.next`, `node_modules` and the tsbuildinfo file); upgrade `next` and `eslint-config-next` to the latest 16.x (≥ 16.2.11) (16.3.8; pnpm 12 with `allowBuilds` in `pnpm-workspace.yaml`; unchanged copy: 466 unit tests pass, lint 0 errors, build compiles; type errors only in II interview tests, deleted next)
- [x] Delete the interview, company, technology, meeting, search, dashboard, cost, daily-report, ingestion-admin and API-key code, plus the branch provider, switcher and lib (78 files left in `src`/`tests`; kept `ProcessingStatusPanel` for Admin and the generic helpers Pagination, DateRangeFilter, LoadingSpinner, useDebounce, useScrollRestore, `lib/download`; `score-utils` deleted)
- [x] Prune `lib/constants.ts`; redirect after login to `/`; new sidebar nav (Risk board, Actions, Admin, Settings); `role` replaces `branch`/`access_level` (`lib/roles.ts` mirrors `Role`/`GLOBAL_ROLES`; Admin link for global roles only, others get a no-access message; queue panel shows generic job kinds, no links)
- [x] Empty dashboard: Risk board placeholder at `/`, Actions placeholder (`app/page.tsx`, `app/actions/page.tsx`; done with the task above because the old home page linked to the removed dashboard route)
- [x] Rebrand (app name, metadata, login copy, e2e heading) (`APP_NAME` "PMO Intelligence", `APP_TAGLINE` "Live health for every consultant placement" in `lib/constants.ts`, used by metadata and the login page)
- [x] Add Prettier, `format` and `typecheck` scripts, the `packageManager` field and `engines`; drop unused dependencies (Prettier 3.9.9 defaults + `eslint-config-prettier`, one format pass over all files incl. `ui/`; `format`, `format:check`, `typecheck` scripts; `packageManager` `pnpm@12.6.0`, engines node >=22, pnpm >=12; dropped date-fns, react-markdown, remark-gfm, @tailwindcss/typography)
- [x] Tests: keep the generic unit tests, rewrite the Sidebar, AuthProvider, layout and callback tests; e2e auth only (86 unit tests in 17 files; new `roles`, `AdminView` tests; generic tests' sample data made PMO; e2e: setup lands on the risk board, 8 role-agnostic auth specs, listed with `playwright test --list` but not run: no local stack until Phase 3)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md`: frontend layout and auth flow
- [x] `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`

**Commit checkpoint**
- [x] `feat: add frontend skeleton with SSO sign-in and empty dashboard` (ef19b70 + 1db2a10; typecheck 0, 86 unit tests, lint clean, format:check clean, build green; e2e listed, not run until Phase 3)

### Phase 3: Local dev and CI
**Code work**
- [x] `docker-compose.yml`, `Makefile` (format fixed, mypy in lint, seed removed), `.env.example`, `.dockerignore` (compose db `pmo_intelligence`, ports as II, `docker compose config` valid; Makefile adds `test-e2e`, lint = ruff + `mypy app` / eslint + typecheck + format:check, both pass; `.env.example` lists only what `config.py` reads, copy to `backend/.env`; `backend/` and `frontend/` `.dockerignore`)
- [x] Dockerfiles (backend without the WeasyPrint libraries) (backend: II's minus WeasyPrint, uv 0.9.18; frontend: pnpm 12.6.0, copies `pnpm-workspace.yaml`, `HOSTNAME=0.0.0.0` so the in-container health check reaches the server; `docker compose up --build` all healthy, `make migrate` applied 001, first e2e run 9/9 after fixing an ambiguous heading locator in `auth.spec.ts`)
- [x] `ci.yml`: default token checkout, mypy, e2e with local auth (`.github/workflows/ci.yml`: latest action majors, uv 0.9.18, pnpm from `packageManager`, Node 22; backend ruff + `mypy app` + unit + integration; frontend eslint + typecheck + format:check + vitest + build; e2e on the compose stack; path filters; actionlint clean; first GitHub run on the phase push)
- [x] Deploy workflow: ECR `pmo-intelligence-*`; deploys only after CI succeeds; `develop` deploys to staging (`deploy-staging` job in `ci.yml`: needs every CI job passed or skipped, push to `develop` only, redeploys the side that changed since the branch's previous commit, OIDC role and identifiers from repository variables, skipped while `vars.AWS_ROLE_ARN` is unset; `main` → prod added at product Phase 5; actionlint clean)

**Doc updates (concurrent)**
- [ ] `README.md` (quick start), `ARCHITECTURE.md` (CI/CD), `CHANGELOG.md`

**Commit checkpoint**
- [ ] `chore: add docker compose, makefile and ci pipeline`; push; **CI green on `develop`**

### Phase 4: Infrastructure as code (plan first, apply only with approval)
**Code work**
- [ ] `infra/bootstrap/`: state bucket (versioned, encrypted, public access blocked)
- [ ] `infra/`: copied `*.tf` renamed for PMO; S3 backend with `use_lockfile`; data sources only for the two account-wide pieces that cannot be duplicated: the `itcapp.ai` Route 53 zone and the GitHub OIDC provider
- [ ] Network: own VPC, subnets in two AZs, routing, and the VPC endpoints the tasks need (open for Phase 4 planning: public subnets with task public IPs vs private subnets with NAT; which endpoints)
- [ ] Own RDS PostgreSQL 16 instance with its security group (open for Phase 4 planning: one instance for staging and prod databases vs one per environment; instance size)
- [ ] Per product: ECS cluster, 2 ALBs, security groups, target groups, 2 ACM certificates, 2 CNAMEs, ECR, task definitions with migration init, services, log groups, 2 secrets, S3 bucket, IAM roles (OIDC role for `Abhishekkv99/pmo-intelligence`)
- [ ] `scripts/db_bootstrap.py` (one-off ECS task): PMO databases on PMO's own instance, a `pmo_app` login role, the vector extension
- [ ] Expiry reminders: SNS email topic plus EventBridge Scheduler (`credential_expiries`)
- [ ] `terraform plan` reviewed with the user; on explicit approval, apply the shared and staging resources (prod behind a variable, applied at Phase 5 of the product)

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md`: what PMO owns versus what it looks up, state backend, database isolation
- [ ] New `docs/DEPLOYMENT.md`: bootstrap order, secret keys, DB bootstrap, rollback
- [ ] `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add terraform for staging and prod with remote state` (before apply; a follow-up commit after apply)

### Phase 5: SSO, staging deploy, audit and handover
**Code work and setup**
- [ ] Entra SSO app "PMO Intelligence": multi-tenant plus allowlist, redirect URIs (localhost and staging), client secret with its expiry recorded
- [ ] User populates the staging secret (values never in chat); `BOOTSTRAP_ADMIN_EMAILS`
- [ ] Run the DB bootstrap for staging; push to `develop`; CI, then deploy
- [ ] Exit gate: sign in at the staging URL with SSO; record the Teams ticket number

**Doc updates (concurrent)**
- [ ] `SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-00-handover.md`, `BACKLOG.md`, `ROADMAP.md`, `TEAMS-GRAPH-SETUP.md`

**Commit checkpoint**
- [ ] `docs: complete sprint 0 audit and handover`

>>> CURRENT PHASE: Phase 3 — Local dev and CI

## Session State (last updated: 2026-10-07 09:40)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Phase 3 — Local dev and CI (Phases 1 and 2 done)
- **Phase progress**: Phase 3 4 of 6
- **Last completed task**: Phase 3 task 4: `deploy-staging` job in `.github/workflows/ci.yml`
- **Next task**: Phase 3 doc updates: `README.md` (quick start: make via winget, `.env.example` → `backend/.env`, `make dev-build`, `make migrate`, `make test-e2e`), `ARCHITECTURE.md` (local dev and CI/CD as built), `CHANGELOG.md`; then the phase commit and the push to `develop` (fix the git credential first, see Blockers) and CI green
- **Last commit**: 7329643 "ci: add workflow for lint, tests and e2e on the compose stack"
- **Uncommitted changes**: none
- **Blockers**: Teams connector app pending tenant admin approval (external; affects only the exit-gate ticket item). Push: the repo is private under `Abhishekkv99`; the default git login and the active `gh` account (`abhishekitc`) cannot see it. User decision 2026-10-07: do not change the default git login or the active `gh` account; push with `Abhishekkv99`'s token for that one command only (`git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`)
- **Tests passing**: 241 unit + 33 integration (backend) + 86 frontend unit + 9 e2e (first local run against compose) = 369; `make lint` passes
- **Files created this session**: `docker-compose.yml`, `Makefile`, `.env.example`, `backend/.dockerignore`, `frontend/.dockerignore`, `backend/Dockerfile`, `.github/workflows/ci.yml`
- **Files modified this session**: `frontend/Dockerfile`, `frontend/tests/e2e/auth.spec.ts`, `docs/planning/CURRENT-SPRINT.md`, `docs/planning/BACKLOG.md`
- **Key decisions this session**: make via winget; compose ports as II; lint gates as CI; one `.dockerignore` per build context; mypy over `app` only; uv 0.9.18 pinned (see Decisions Log)
- **Recovery instructions**: Phase 3 tasks 1–2 written (54f9ee1, ffecbab, then the Dockerfile commit; check `git log`). Local stack: `make dev-build` (or `docker compose up -d --build`), `make migrate`, `make test-e2e`. make lives at `%LOCALAPPDATA%\Microsoft\WinGet\Packages\ezwinports.make_*\bin` (on the user PATH; a shell opened before the install needs it prepended). Next: `ci.yml`, deploy workflow, then README/ARCHITECTURE/CHANGELOG and the phase commit. Deleting files needs the user to run the command (the tool permission layer denies `rm`).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Python deps via uv, frontend via pnpm | Matches the Interview Intelligence repo (`backend/uv.lock`, `frontend/pnpm-lock.yaml`); npm was the first answer, corrected 2026-10-06 after checking the repo |
| Dev/test/lint/format via Makefile targets (`make dev`, `make test`, `make lint`, `make format`) | Confirmed against the II Makefile; `format` and `seed` are broken there and fixed or removed here |
| `docs/PRD.md` is a complete, verbatim conversion of the kickoff Project Starter document | The kickoff document is the core spec; nothing in it may be lost or paraphrased |
| Sprint 0 = Phase 0 (Bootstrap) | Matches the PRD's phased delivery plan |
| Local-only developer config is excluded via `.git/info/exclude`, not `.gitignore` | Keeps the committed ignore file to project concerns only |
| Teams groups: one group chat per consultant (BACKLOG #1) | User decision; matches the PRD's suggested answer |
| Teams permission route: RSC with `Chat.Read.All` fallback in parallel (BACKLOG #4) | User decision; RSC is least-privileged and visible to chat members |
| GitHub repo `Abhishekkv99/pmo-intelligence`, private | User decision; same owner as Interview Intelligence |
| UK only; all UK/US branch logic removed | User decision (#9) |
| Roles replace branch entitlement; new SSO users have no role until assigned; bootstrap admins become `pmo_manager` | PRD roles and server-side scope; no access by default |
| Dedicated `pmo_app` database role (application login, not the master user) | Least privilege for the app. Originally for the shared RDS instance (blast radius, #8); kept on PMO's own instance after the 2026-10-07 revision |
| **Fully separate AWS infrastructure from Interview Intelligence** (supersedes the shared RDS instance and shared default VPC of #8) | User decision 2026-10-07. PMO owns its VPC, subnets, VPC endpoints, RDS instance, ECS cluster, ALBs, certificates, ECR, bucket, secrets, IAM roles and Terraform state. Shared only where AWS allows one per account or the domain is one: the `itcapp.ai` Route 53 zone (PMO adds its own records) and the GitHub OIDC provider (PMO gets its own role, scoped to its repo). No PMO resource or rule is attached to any II resource |
| Deploy only after CI succeeds | II deploys even when CI fails |
| CI checks out with the default `GITHUB_TOKEN` | A same-repo checkout needs no PAT, so there is no token expiry to track |
| Prod infra defined but applied at the product's Phase 5 | Avoids idle prod ALB cost before the first release |
| pnpm 12 (not II's pnpm 10) for `packageManager`, CI and Docker | User decision 2026-10-06; matches the local toolchain. pnpm 12 ignores the `pnpm` field in `package.json`, so build approvals live in `pnpm-workspace.yaml` `allowBuilds` (esbuild allowed; msw, unrs-resolver denied) |
| Frontend deps: drop date-fns, react-markdown, remark-gfm, @tailwindcss/typography; keep zod, @hookform/resolvers, @tanstack/react-table | User decision 2026-10-06; nothing imports the dropped ones; forms (register) and TanStack tables (risk board) come next sprint |
| Prettier 3 defaults over every file, `ui/` included, with `eslint-config-prettier` | User decision 2026-10-06; lets `format:check` gate CI |
| `engines` node >=22, pnpm >=12; `packageManager` pnpm@12.6.0 | User decision 2026-10-06; Node 22 matches II's CI and Docker image; corepack needs an exact version |
| Tagline "Live health for every consultant placement" | User decision 2026-10-06; from the PRD purpose line |
| Admin link hidden from non-global roles; `/admin` shows them a no-access message and never requests the queue | User decision 2026-10-06; the backend answers 403 to them |
| Admin page keeps II's `ProcessingStatusPanel` (pmo_manager/admin only); generic helpers kept, `score-utils` deleted | User decision 2026-10-06; the backend already serves `/processing/status`; the risk board and actions need the helpers; score-utils' 0.7/0.4 cutoffs conflict with the configured RAG thresholds |
| Next.js 16.3.8 (latest 16.x on 2026-10-06), React kept at 19.2.3 | Clears the 16.0.0–16.2.10 CVEs; React 19.2.3 is within Next's peer range, so no React upgrade in Sprint 0 |
| GNU make installed locally with `winget install ezwinports.make`; the Makefile stays POSIX (Git Bash locally, Ubuntu in CI) | User decision 2026-10-06; make was not on the Windows dev machine; one Makefile, no PowerShell twin |
| Compose host ports as II: 5432 (db), 8000 (api), 3000 (web) | User decision 2026-10-06; matches the config defaults, the SSO redirect URI and Playwright; the two stacks cannot run at once |
| `make lint` frontend = eslint + typecheck + format:check; backend = ruff check + ruff format --check + `mypy app` | User decision 2026-10-06; the same gates CI runs. mypy covers `app` only: `app tests` has 57 errors in 8 test files (tech debt) |
| uv pinned to exactly 0.9.18 in the backend Dockerfile (`ghcr.io/astral-sh/uv:0.9.18`) and in CI | User decision 2026-10-07; `uv.lock` is revision 3, written by local uv 0.9.18; II's `uv:0.6` predates that format. Bumped deliberately, like pnpm 12.6.0 |
| CI uses the latest action majors: checkout v7, setup-node v7, upload-artifact v7, setup-uv v10, pnpm/action-setup v6, paths-filter v4 | User decision 2026-10-07; all on the node24 runtime (II's v4-era pins run on node20, being retired) |
| CI e2e runs against the docker compose stack (images built in the job, migrations from the runner, then Playwright) | User decision 2026-10-07; same path as `make dev-build` + `make migrate` + `make test-e2e`, and it exercises the Dockerfiles (the HOSTNAME bug would have been caught) |
| CI keeps II's path filters (backend, frontend; e2e on either, plus compose and the workflow) | User decision 2026-10-07; docs-only pushes run nothing and CI still succeeds, so the deploy gate passes |
| Deploy is a `deploy-staging` job inside `ci.yml` that needs every CI job (passed or skipped) and runs on push only | User decision 2026-10-07; same run and commit sha as the checks; only that job gets `id-token: write`. A separate `workflow_run` file would run from the default branch's copy and need the sha checked out by hand |
| Only `develop` → staging is wired in Sprint 0; `main` → production is added when prod infra is applied (product Phase 5) | User decision 2026-10-07; a push to `main` cannot fail on ECS services that do not exist yet |
| Deploy identifiers are repository variables (`vars.AWS_ROLE_ARN`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER_NAME`, `ECS_STAGING_BACKEND_SERVICE`, `ECS_STAGING_FRONTEND_SERVICE`); no repository secrets | User decision 2026-10-07; none are secret with OIDC, and readable values make failures easy to diagnose. GitHub Environments would need GitHub Pro on a private repo. Values come from the Phase 4 Terraform outputs |
| One `.dockerignore` per build context (`backend/`, `frontend/`), tests excluded from images | User decision 2026-10-06; compose builds from `./backend` and `./frontend`, so a root file would not apply |
