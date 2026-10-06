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
- [ ] Copy the generic backend files as-is (pyproject/uv.lock, alembic env, db session and base repository, user and refresh-token models, LLM factory, cost tracker, exceptions, memory, security middleware, rate limiter, auth routes and services, health and processing-status routes)
- [ ] Rewrite `processing_queue.py` (generic core with an injected runner registry) and `processing_ownership.py` (injectable sweeps)
- [ ] Rewrite `dependencies.py`, `main.py` (lifespan: bootstrap admins, then `hold_processing`), `config.py` (PMO names) and `api/router.py`
- [ ] Role model: nullable `users.role` (`pmo_manager | sme | tech_lead | ps | admin`); bootstrap admins raised to `pmo_manager`; new SSO users get no role
- [ ] Scope foundation: `Principal`, `require_placement_scope` (404 plus a WARNING), `access_log` writer, route-coverage test
- [ ] Migration 001: vector extension plus users, refresh_tokens, consultants, clients, projects, placements, processing_jobs, processing_costs, access_log
- [ ] Prune dependencies (drop the unused second LLM SDK and the report/teams-matching libraries: fpdf2, weasyprint, rapidfuzz, markdown, xlsxwriter) and run `uv lock`
- [ ] Tests: adapt both conftests and the kept II tests; add entitlement, coverage, access-log and migration smoke tests; mypy strict passes

**Doc updates (concurrent)**
- [ ] `docs/ARCHITECTURE.md`: backend layout, role model, migration 001 as built
- [ ] `docs/API.md`: health, auth, processing-status endpoints
- [ ] `docs/tracking/TESTS.md`, `FEATURES.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add backend skeleton with auth, role scope and migration 001` (`make test-backend` and `make lint` green; tool-reference scan clean)

### Phase 2: Frontend skeleton
**Code work**
- [ ] Copy the frontend (without `.next`, `node_modules` and the tsbuildinfo file); upgrade `next` and `eslint-config-next` to the latest 16.x (≥ 16.2.11)
- [ ] Delete the interview, company, technology, meeting, search, dashboard, cost, daily-report, ingestion-admin and API-key code, plus the branch provider, switcher and lib
- [ ] Prune `lib/constants.ts`; redirect after login to `/`; new sidebar nav (Risk board, Actions, Admin, Settings); `role` replaces `branch`/`access_level`
- [ ] Empty dashboard: Risk board placeholder at `/`, Actions placeholder
- [ ] Rebrand (app name, metadata, login copy, e2e heading)
- [ ] Add Prettier, `format` and `typecheck` scripts, the `packageManager` field and `engines`; drop unused dependencies
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

>>> CURRENT PHASE: Phase 1 — Backend skeleton

## Session State (last updated: 2026-10-06 16:30)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Phase 1 — Backend skeleton
- **Phase progress**: 0 of 8 tasks complete
- **Last completed task**: Sprint 0 plan approved and written here
- **Next task**: Phase 1: copy the generic backend files from Interview Intelligence
- **Last commit**: 87c71ff "chore: add Teams Graph access setup scripts and app package"
- **Uncommitted changes**: this plan
- **Blockers**: Teams connector app pending tenant admin approval (external; affects only the exit-gate ticket item)
- **Tests passing**: 0 unit + 0 integration + 0 frontend = 0 (no code yet)
- **Files created this session**: none yet in Sprint 0
- **Files modified this session**: `docs/planning/CURRENT-SPRINT.md`, `docs/planning/BACKLOG.md`
- **Key decisions this session**: see User Decisions Made
- **Recovery instructions**: Work on `develop`. Source repo `E:\E Projects\Interview Intelligence Platform`. Never copy its `infra/terraform.tfstate*`, `terraform.tfvars` or `.terraform/`. Start Phase 1 with the "copy as-is" files, then the rewrites.

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
