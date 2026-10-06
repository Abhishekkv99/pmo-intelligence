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
| Environments and database (#8) | Staging + prod, each with its own database on the shared RDS instance | Staging only; own RDS instance |
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
- [ ] Tests: keep the generic unit tests, rewrite the Sidebar, AuthProvider, layout and callback tests; e2e auth only

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md`: frontend layout and auth flow
- [ ] `TESTS.md`, `FEATURES.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add frontend skeleton with SSO sign-in and empty dashboard` (tests, lint, typecheck and build green)

### Phase 3: Local dev and CI
**Code work**
- [ ] `docker-compose.yml`, `Makefile` (format fixed, mypy in lint, seed removed), `.env.example`, `.dockerignore`
- [ ] Dockerfiles (backend without the WeasyPrint libraries)
- [ ] `ci.yml`: default token checkout, mypy, e2e with local auth
- [ ] Deploy workflow: ECR `pmo-intelligence-*`; deploys only after CI succeeds; `develop` deploys to staging

**Doc updates (concurrent)**
- [ ] `README.md` (quick start), `ARCHITECTURE.md` (CI/CD), `CHANGELOG.md`

**Commit checkpoint**
- [ ] `chore: add docker compose, makefile and ci pipeline`; push; **CI green on `develop`**

### Phase 4: Infrastructure as code (plan first, apply only with approval)
**Code work**
- [ ] `infra/bootstrap/`: state bucket (versioned, encrypted, public access blocked)
- [ ] `infra/`: copied `*.tf` renamed for PMO; S3 backend with `use_lockfile`; data sources for the default VPC, Route 53 zone, OIDC provider, II RDS and its security group, and the VPC-endpoint security group
- [ ] Per product: ECS cluster, 2 ALBs, security groups, target groups, 2 ACM certificates, 2 CNAMEs, ECR, task definitions with migration init, services, log groups, 2 secrets, S3 bucket, IAM roles (OIDC role for `Abhishekkv99/pmo-intelligence`)
- [ ] Additive security-group rules on the II RDS and VPC-endpoint security groups
- [ ] `scripts/db_bootstrap.py` (one-off ECS task): PMO databases, a `pmo_app` login role, the vector extension
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

>>> CURRENT PHASE: Phase 2 — Frontend skeleton

## Session State (last updated: 2026-10-06 17:03)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Phase 2 — Frontend skeleton (Phase 1 done)
- **Phase progress**: 6 of 10 tasks complete
- **Last completed task**: Prettier, scripts, packageManager/engines, unused deps dropped; typecheck 0, 83 unit tests, lint 0 errors, format:check clean, build green
- **Next task**: Tests: keep the generic unit tests, rewrite the Sidebar, AuthProvider, layout and callback tests; e2e auth only
- **Last commit**: 9e233e0 "docs: mark phase 1 complete in sprint plan"
- **Uncommitted changes**: `frontend/` (new), `docs/planning/CURRENT-SPRINT.md`
- **Blockers**: Teams connector app pending tenant admin approval (external; affects only the exit-gate ticket item)
- **Tests passing**: 241 unit + 33 integration (backend) + 83 frontend unit = 357
- **Files created this session**: `backend/` (copied from Interview Intelligence and adapted; new: `app/models/enums.py`, `app/models/register.py`, `app/models/access_log.py`, `app/db/repositories/access_log_repo.py`, `alembic/versions/001_create_initial_schema.py`, `tests/unit/test_entitlements.py`, `tests/unit/test_entitlement_coverage.py`, `tests/integration/test_placement_scope.py`, `tests/integration/test_migrations.py`)
- **Files modified this session**: `.gitignore` (adopted II's Python/Node/Terraform ignores, tool lines dropped), the docs listed above
- **Key decisions this session**: queue tiers chat < session < backlog; runners and takeover steps are registered by the owning module (no imports from pipelines into the queue); a placement-id route must carry a placement-scope guard specifically (coverage test); processing_jobs is generic (`kind`, `subject_id`)
- **Recovery instructions**: Phase 1 code and docs are complete and verified (ruff, mypy strict, 274 tests). Commit them, then start Phase 2 by copying the II frontend (without `.next`, `node_modules`, tsbuildinfo) and upgrading Next.js to ≥16.2.11.

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
| Dedicated `pmo_app` database role on the shared RDS instance | PMO cannot read or alter Interview Intelligence data (blast radius, #8) |
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
