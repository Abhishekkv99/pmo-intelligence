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
- **Sandbox account survey (2026-10-07, `pmo-intelligence` profile, read-only)**: account `260172548683` holds only the default VPC (`172.31.0.0/16`). No Route 53 zones (so no `itcapp.ai`), no IAM OIDC provider, and no RDS, ECS, ECR, ALB, ACM, S3, NAT, Elastic IP or CloudFormation stacks. Nothing to clash with; PMO creates everything.
- **Entra redirect URIs** must be HTTPS except for `localhost`, so staging SSO needs a domain with a certificate.
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
- [x] (Discovered) Configurable host ports `PMO_API_PORT`/`PMO_WEB_PORT` (defaults 8000/3000) in compose, the Makefile and `make test-e2e`, so the stack runs beside another project's dev servers (e2e 9/9 on 8100/3100 with the other servers on 8000/3000)

**Doc updates (concurrent)**
- [x] `README.md` (quick start), `ARCHITECTURE.md` (CI/CD), `CHANGELOG.md` (new `README.md`: prerequisites, quick start, commands, CI; `ARCHITECTURE.md` "Local development and CI/CD (as built)"; `CHANGELOG.md`; also `TESTS.md`: 369 from the 2026-10-07 run, e2e 9 against compose)

**Commit checkpoint**
- [x] `chore: add docker compose, makefile and ci pipeline`; push; **CI green on `develop`** (deviation: the code went in as smaller commits 54f9ee1, ffecbab, 46ea4b7, 7329643, 5e2a851, f4ff059; phase commit cde4aec; first run 37577785017 failed at job setup on `setup-uv@v10`, fixed in 164e95a; run 37578107788 green: 241 unit + 33 integration + 86 frontend unit + 9 e2e, deploy skipped)

### Phase 4: Infrastructure as code (plan first, apply only with approval)
**Code work**
- [x] `infra/bootstrap/`: state bucket (versioned, encrypted, public access blocked) (applied 2026-10-07: `pmo-intelligence-tfstate-260172548683`, 7 resources, plus SSE-S3, TLS-only policy, 90-day noncurrent expiry, `prevent_destroy`; own state migrated to `bootstrap/terraform.tfstate`; plan clean)
- [x] Main Terraform, adapted from II's `infra/*.tf`, (written 2026-10-07, 71778f2; shared applied: 23 resources, VPC `vpc-07b4916ad2aaa890c`; staging step 1 applied: hosted zone, name servers `ns-1004.awsdns-61.net`, `ns-1450.awsdns-53.org`, `ns-1905.awsdns-46.co.uk`, `ns-4.awsdns-00.com`; staging step 2 waits for the NS delegation) all in account `260172548683` with S3 backends (`use_lockfile`): `infra/shared/` (state `shared/`: VPC, subnets, S3 endpoint, ECR with lifecycle, ECS cluster, GitHub OIDC provider and deploy role, deny-deletion policy), `infra/modules/environment/` (ALB with HTTP→HTTPS redirect, target groups, security groups, RDS, app secret, log groups, task definitions, services, hosted zone, certificate, SES identity, media bucket, IAM roles) and `infra/environments/staging/` (state `staging/`); staging step 2 applied 2026-10-07: 51 resources, `https://pmo-intelligence-staging.itcapp.ai` serves the certificate, re-plan shows no changes
- [x] DNS: public hosted zone `pmo-intelligence-staging.itcapp.ai` in the sandbox, its name servers as an output; ACM certificate validated in that zone; ALB alias record. External step: whoever manages `itcapp.ai` adds one NS record delegating that name (BACKLOG). Prod gets its own delegated zone at product Phase 5 (done: NS record added 2026-10-07 in account `430006376054`, verified)
- [x] Network: own VPC in two AZs; public subnets for the ALBs and the ECS tasks (public IPv4 per task, inbound only from the ALB security group), private subnets with no internet route for RDS; internet gateway; S3 gateway endpoint; no NAT, no interface endpoints (done in `infra/shared/`)
- [x] Own RDS PostgreSQL 16 instance for staging: `db.t4g.micro`, single-AZ, 20 GB gp3, private subnets, security group open only to the backend tasks; production gets its own instance at product Phase 5 (done: `pmo-intelligence-staging`, created in 9 min)
- [x] Per product: ECS cluster, 2 ALBs, security groups, target groups, 2 ACM certificates, 2 DNS records (alias in the delegated zones), ECR, task definitions with migration init, services, log groups, 2 secrets, S3 bucket, IAM roles (OIDC role for `Abhishekkv99/pmo-intelligence`) (staging done via `infra/modules/environment/`; prod at product Phase 5)
- [x] `scripts/db_bootstrap.py` (one-off ECS task): PMO databases on PMO's own instance, a `pmo_app` login role, the vector extension (written 2026-10-07 as `backend/app/cli/db_bootstrap.py` + `scripts/db-bootstrap.sh` + `make db-bootstrap`; Terraform task definition and roles in `infra/modules/environment/db_bootstrap.tf` planned: 7 to add; 11 unit + 5 integration tests pass; applied and run on staging 2026-10-07: `pmo_app` created, owns `pmo_intelligence`, `DATABASE_URL` written; backend redeployed, migration 001 ran as `pmo_app`)
- [x] (Discovered 2026-10-08) Azure OpenAI for PMO as Terraform (`infra/azure/`): own resource group `rg-pmo-intelligence-swc` and resource `oai-pmo-intelligence-swc` (Sweden Central), Data Zone Standard deployments `gpt-5.4-mini-staging` and `text-embedding-3-small-staging` at 50K TPM (planned: 5 to add with the group-scoped policy exemption; first apply blocked twice: MFA claim, fixed with a device-code login with the claims challenge; then the resource-group creation policy, waiting for the policy owner's agreement to a 2-hour exemption); applied 2026-10-08 with the policy owner's agreement: 2-hour subscription waiver created, 5 resources applied, waiver deleted 3 minutes later; re-plan clean; endpoint, deployments and key piped into `pmo-intelligence/staging/app` (key never shown); smoke test: chat answered, embeddings 1536-dimension; backend redeployed and healthy
- [x] Expiry reminders: SNS email topic plus EventBridge Scheduler (`credential_expiries`) (written 2026-10-08 in `infra/shared/expiry_reminders.tf`: 30/14/3 days before, 09:00 Europe/London, to Abhishek.Verma@InformationTechConsultants.com; Teams Graph certificate 2027-10-06 tracked; committed 1d14675 and applied 2026-10-08: 3 schedules enabled, subscription confirmed, 1 test email delivered (SNS metric); re-plan of `infra/shared/` shows no changes)
- [x] `terraform plan` reviewed with the user; on explicit approval, apply the shared and staging resources (prod behind a variable, applied at Phase 5 of the product) (bootstrap, shared and staging plans reviewed and applied with approval 2026-10-07)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md`: what PMO owns versus what it looks up, state backend, database isolation ("Infrastructure (as built)": nothing on AWS shared, the NS delegation the only outside link; state bucket and keys; staging's own RDS instance and `pmo_app`; Azure OpenAI and the reminders; checked 2026-10-08)
- [x] New `docs/DEPLOYMENT.md`: bootstrap order, secret keys, DB bootstrap, rollback (access via SSO, tooling, sections 1–6 for every stack, app secret key table, app-deploy rollback by image retag plus `git revert` with the migration caveat (user decision 2026-10-08), state rollback)
- [x] `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add terraform for staging and prod with remote state` (before apply; a follow-up commit after apply)

### Phase 5: SSO, staging deploy, audit and handover
**Code work and setup**
- [ ] Entra SSO app "PMO Intelligence": multi-tenant plus allowlist, redirect URIs (localhost and staging), client secret with its expiry recorded
- [ ] User populates the staging secret (values never in chat); `BOOTSTRAP_ADMIN_EMAILS` (Azure OpenAI values piped in and the AssemblyAI key set 2026-10-08; Entra values left; add the Entra client secret's expiry date to `credential_expiries`)
- [ ] Run the DB bootstrap for staging; push to `develop`; CI, then deploy
- [ ] Exit gate: sign in at the staging URL with SSO; record the Teams ticket number

**Doc updates (concurrent)**
- [ ] `SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-00-handover.md`, `BACKLOG.md`, `ROADMAP.md`, `TEAMS-GRAPH-SETUP.md`

**Commit checkpoint**
- [ ] `docs: complete sprint 0 audit and handover`

>>> CURRENT PHASE: Phase 4 — Infrastructure as code (all code and doc tasks done; phase commit left)

## Session State (last updated: 2026-10-08 10:42)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Phase 4 — Infrastructure as code (Phases 1–3 done)
- **Phase progress**: Phase 4 all 9 code tasks and 3 doc tasks done; phase commit left
- **Last completed task**: expiry reminders verified as applied (re-plan clean, subscription confirmed, test email delivered); Phase 4 doc check: `DEPLOYMENT.md` status line, app secret key table, app-deploy rollback; `CHANGELOG.md`
- **Next task**: Phase 4 commit (docs) and push; then STOP. Phase 5 starts with the Entra SSO app "PMO Intelligence" when the user asks
- **Last commit**: 1d14675 "feat: email reminders before credentials expire" (pushed)
- **Uncommitted changes**: `docs/DEPLOYMENT.md`, `docs/tracking/CHANGELOG.md`, `docs/planning/CURRENT-SPRINT.md`
- **Blockers**: Teams connector app pending tenant admin approval (external; affects only the exit-gate ticket item). Push: the repo is private under `Abhishekkv99`; the default git login and the active `gh` account (`abhishekitc`) cannot see it. User decision 2026-10-07: do not change the default git login or the active `gh` account; push with `Abhishekkv99`'s token for that one command only (`git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`). AWS: run `aws sso login --profile pmo-intelligence` when the session expires
- **Tests passing**: 252 unit + 38 integration (backend) + 86 frontend unit + 9 e2e = 385 (2026-10-07); `make lint-backend` passes
- **Files created this session**: `docker-compose.yml`, `Makefile`, `.env.example`, `backend/.dockerignore`, `frontend/.dockerignore`, `backend/Dockerfile`, `.github/workflows/ci.yml`, `README.md`, `infra/bootstrap/{versions,variables,main,outputs}.tf`, `infra/bootstrap/.terraform.lock.hcl`, `infra/bootstrap/backend.tf`, `docs/DEPLOYMENT.md`
- **Files modified this session**: `frontend/Dockerfile`, `frontend/tests/e2e/auth.spec.ts`, `docs/planning/CURRENT-SPRINT.md`, `docs/planning/BACKLOG.md`, `.gitignore` (recursive Terraform rules, lock file tracked)
- **Key decisions this session**: make via winget; compose ports as II; lint gates as CI; one `.dockerignore` per build context; mypy over `app` only; uv 0.9.18 pinned (see Decisions Log)
- **Audit notes (Rule C, for the sprint audit)**: (1) CI used `astral-sh/setup-uv@v10`, a tag that does not exist; the first run failed at job setup. Cause: assumed every action publishes a floating major tag. Rule to add: verify every `uses:` ref with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` before pushing a workflow. (2) The docs said docs-only pushes skip CI on `develop`; paths-filter compares a non-default-branch push with `main`. Cause: the II comment about `base` was read for the deploy filter only. Rule to add: state the comparison base whenever a doc describes path-filtered behaviour. (3) The e2e re-run failed when another project's dev servers held 8000/3000; fixed with configurable ports (4) The Terraform ignore rule matched only `tfplan`, so a saved plan named `tfplan-zone` (state data) showed as untracked; widened to `tfplan*` before any commit. Rule to add: name saved plans `tfplan*` and check `git status --untracked-files=all infra/` after every plan (5) The first deploy failed at OIDC sign-in: the role trusted `repo:Abhishekkv99/pmo-intelligence:ref:...`, but the repository issues GitHub's immutable subject `repo:Abhishekkv99@28754691/pmo-intelligence@1407046286:ref:...`. Cause: II's trust condition was copied without reading the repository's OIDC settings. Rule to add: read `gh api repos/<owner>/<repo>/actions/oidc/customization/sub` before writing a trust policy. (6) `docker login` to ECR fails with the Windows credential store ("The stub received bad data"); a temporary `DOCKER_CONFIG` holding the auth entry works (7) `make db-bootstrap` failed on Windows: make passed the script's path, which contains a space, unquoted to bash; the target now runs `bash scripts/db-bootstrap.sh`. Rule to add: Makefile targets call scripts through their interpreter (8) The Azure apply was blocked twice: Azure requires an MFA claim for writes (the Windows account broker signed in silently without one), then a subscription policy denies non-managed resource groups. Cause: the subscription's write requirements and policies were not read before planning. Rule to add: before an Azure plan, list `az policy assignment list` and test the login's MFA claim (9) `az policy exemption create --scope /subscriptions/...` failed with MissingSubscription: Git Bash rewrote the leading `/subscriptions/` into a Windows path. Rule to add: set `MSYS_NO_PATHCONV=1` for any CLI argument that starts with `/` (Azure scopes, CloudWatch log groups) (10) The Session State block was written at 02:45 before the reminders commit and apply and not refreshed after, so the next session read "last commit 2b28a77" and "next: commit and apply" for work already done. Cause: the block was updated ahead of the actions it described. Rule to add: refresh Session State after each commit, push and apply, never in advance of them
- **Recovery instructions**: Phases 1–3 are committed and pushed; CI is green on `develop`. Local stack: `make dev-build`, `make migrate`, `make test-e2e` (add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` to each when another project holds 8000/3000). make lives at `%LOCALAPPDATA%\Microsoft\WinGet\Packages\ezwinports.make_*\bin`. Push and `gh` calls use Abhishekkv99's token per command (see Blockers), never a default login change. Phase 4 starts with the open questions above; infra is fully separate from II (Decisions Log). Deleting files needs the user to run the command (the tool permission layer denies `rm`).

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
| **Fully separate AWS infrastructure from Interview Intelligence** (supersedes the shared RDS instance and shared default VPC of #8) | User decision 2026-10-07. PMO owns its VPC, subnets, VPC endpoints, RDS instance, ECS cluster, ALBs, certificates, ECR, bucket, secrets, IAM roles and Terraform state. Shared only where AWS allows one per account or the domain is one: the `itcapp.ai` Route 53 zone (PMO adds its own records) and the GitHub OIDC provider (PMO gets its own role, scoped to its repo). No PMO resource or rule is attached to any II resource. Superseded the same day by the separate sandbox account (rows below): nothing on AWS is shared, the OIDC provider is PMO's own, and the only outside link is the NS record delegating the staging hostname |
| **AWS account: ITC Sandbox PD Intelligence (`260172548683`), eu-west-2**, signed in with SSO through the local profile `pmo-intelligence` (`AdministratorAccess`, its own `sso-session` on the ITC Identity Center portal) | User decision 2026-10-07: infra is created and deployed in this sandbox account. Terraform and scripts run with `AWS_PROFILE=pmo-intelligence`; `aws sso login --profile pmo-intelligence` refreshes the session. The `itcapp.ai` zone and the GitHub OIDC provider assumed earlier must be re-checked in this account before Phase 4 is planned |
| Network: ECS tasks in public subnets with a public IPv4 each, no NAT gateway; RDS in private subnets with no internet route | User decision 2026-10-07; the backend must reach Azure OpenAI, AssemblyAI and Entra outside AWS, so egress is needed either way; public IPs (~$3.65/month per task) cost far less than NAT (~$36/month + data). Task security groups admit only the ALB |
| VPC endpoints: S3 gateway endpoint only | User decision 2026-10-07; free, keeps recording and image-layer traffic to S3 inside AWS; interface endpoints (~$8/month each per AZ) mainly pay off with NAT |
| RDS: a staging-only `db.t4g.micro` (single-AZ, 20 GB gp3, PostgreSQL 16 with pgvector); production gets its own instance at product Phase 5, sized from real load | User decision 2026-10-07; full staging/prod isolation; supersedes the one-instance-for-both plan of #8 |
| Terraform AWS provider `~> 6.0` (v6.67.0 current on 2026-10-07); `.terraform.lock.hcl` committed with linux and windows hashes | User decision 2026-10-07; new code, so no v5→v6 migration later; II's copied `*.tf` adjusted where v6 changed arguments. The lock file pins provider builds for everyone and CI, like `uv.lock` (II ignores it) |
| State bucket `pmo-intelligence-tfstate-260172548683`: SSE-S3, versioning, public access blocked, TLS-only bucket policy, noncurrent versions expire after 90 days; native S3 locking (`use_lockfile`) | User decision 2026-10-07; the account id keeps the global name unique; SSE-S3 is free |
| `infra/bootstrap/` applies with local state once, then migrates its own state into the bucket (key `bootstrap/terraform.tfstate`) | User decision 2026-10-07; no state left on one machine |
| Terraform layout: `infra/shared/` + `infra/modules/environment/` + `infra/environments/staging/`, each root with its own state key | User decision 2026-10-07; no copy-paste between environments (II duplicates prod as `staging.tf`), and a staging apply cannot touch prod. Prod is one more small folder at product Phase 5. Supersedes "one `infra/` with prod behind a variable" |
| RDS master password managed by RDS (`manage_master_user_password`), never in Terraform state; the app connects as `pmo_app`, whose URL the db bootstrap writes into the app secret | User decision 2026-10-07; II generates the password in Terraform and stores it in state and the app secret |
| Deletion protection on data only: RDS (deletion protection, final snapshot, `prevent_destroy`), media bucket, app secret; ALB, services, security groups and logs stay freely replaceable | User decision 2026-10-07; II protects everything, which makes tearing down a sandbox staging slow |
| Carried over from II: HTTP→HTTPS redirect (II forwards plain HTTP to the frontend), ECR lifecycle (untagged 7 days, last 10 tagged), deny-deletion IAM policy (output for attaching to IAM users or groups), SES domain identity now | User decision 2026-10-07 (all four extras) |
| Names `pmo-intelligence-<env>-*`; where AWS caps names at 32 characters (target groups) `pmo-<env>-*`; ECR stays `pmo-intelligence-backend` / `-frontend` | User decision 2026-10-07; `pmo-intelligence-staging-frontend` would be 33 characters |
| VPC `10.40.0.0/16`, /20 subnets: 2 public + 2 private across two AZs | User decision 2026-10-07; avoids the default `172.31.0.0/16` and II's `10.0.0.0/16`, so peering or a VPN to either stays possible |
| Staging tasks as II staging: backend 0.25 vCPU / 1024 MiB, frontend 0.25 vCPU / 512 MiB, one task each, `PROCESSING_CONCURRENCY` 1 | User decision 2026-10-07; II raised the backend to 1024 MiB after OOM kills |
| SES sending domain `pmo-intelligence-staging.itcapp.ai` (DKIM records in the delegated zone); the account starts in the SES sandbox until production access is requested | User decision 2026-10-07 |
| Database bootstrap: `backend/app/cli/db_bootstrap.py` in the backend image, run as a one-off ECS task (`<env>-db-bootstrap` task definition with its own roles) by `make db-bootstrap ENV=staging` | User decision 2026-10-07; RDS is private with no bastion or ECS Exec, and the backend cannot start without `DATABASE_URL`. Supersedes the plan's repo-root `scripts/db_bootstrap.py`, which the backend build context (`backend/`) cannot include |
| The bootstrap generates `pmo_app`'s password and writes `DATABASE_URL` into the app secret itself; only the bootstrap task's roles may read the RDS master secret and write the app secret | User decision 2026-10-07; no person sees the password, and the running app cannot rewrite its own secret |
| Bootstrap re-runs are idempotent and keep the password; `--rotate-password` rotates it and rewrites the secret (then the backend needs a redeploy) | User decision 2026-10-07 |
| `pmo_app` owns the database and its `public` schema (the migration init container runs DDL with the same URL); no superuser; the master user creates the `vector` extension | User decision 2026-10-07; a separate migration role was offered and declined |
| **Azure OpenAI for PMO in its own resource group and resource**, not II's (`rg-interview-intelligence` / `interview-intelligence`, East US); AssemblyAI gets a PMO-only API key | User decision 2026-10-08; cost tracked per resource group, keys rotated or revoked without touching II, own RBAC and lifecycle. A separate resource does not separate quota: TPM quota is per subscription, region, model and deployment type |
| Azure region Sweden Central with **Data Zone Standard** deployments | User decision 2026-10-08; prompts carrying workers' transcripts are processed only inside the EU data zone (UK adequacy). UK South offers `gpt-5.4-mini` only as Global Standard (processed in any region) or provisioned; East US would put the data in the US |
| One Azure resource group and one Azure OpenAI resource for PMO; environments are separate **deployments** (`<model>-staging`, later `<model>-prod`) | User decision 2026-10-08; simplest to manage. Staging and prod share the resource's keys; offered alternatives were one RG per environment and one resource per environment |
| Azure resources as Terraform in this repo (`infra/azure/`, azurerm provider, Azure CLI auth, state in the S3 state bucket) | User decision 2026-10-08; the same plan-review-apply flow as AWS |
| Staging deployments: `gpt-5.4-mini` (2026-03-17) and `text-embedding-3-small` (1536 dimensions, matching `signals.embedding`), each with a small TPM capacity | User decision 2026-10-08 |
| Azure resource-group policy: a time-boxed (2 h) subscription-wide exemption for the one creation, **only with the policy owner's agreement**, deleted right after; Terraform adds a permanent exemption scoped to `rg-pmo-intelligence-swc` alone | User decision 2026-10-08; the subscription's custom policy "Restrict RG Creation to Managed Service Patterns" denies creating or updating any non-managed resource group, Owners included. An exemption cannot target a group that does not exist yet. Alternatives offered: the admin creates the group (Terraform reads it), or an existing group for now |
| App-deploy rollback documented as an ECR retag of a known-good `sha-<commit>` image to `staging-latest` plus a force-new-deployment, then a `git revert` on `develop`; a migration added by the bad deploy is downgraded first with the newer image | User decision 2026-10-08; the retag is minutes, the revert stops the next CI deploy reintroducing the change. Alternatives offered: revert only (a full CI run), retag only |
| Credential expiry reminders: a `credential_expiries` map (name → expiry date) in `infra/shared/`; EventBridge Scheduler one-time schedules at 09:00 Europe/London 30, 14 and 3 days before each date publish to an SNS email topic for `Abhishek.Verma@InformationTechConsultants.com` | User decision 2026-10-08; a daily checker reading Entra through Graph was offered and declined (it would need its own Graph credential). Tracked now: the Teams Graph certificate (2027-10-06); the Entra SSO client secret is added when it is created in Phase 5 |
| GitHub OIDC provider created by PMO's Terraform in the sandbox account | Survey 2026-10-07: none exists in `260172548683` (the II account's provider was the reason for a data source) |
| **Staging hostname by subdomain delegation**: public zone `pmo-intelligence-staging.itcapp.ai` in the sandbox account; one NS record for it in the `itcapp.ai` zone, added by whoever manages that zone | User decision 2026-10-07; `itcapp.ai` is not in the sandbox account and Entra needs HTTPS outside `localhost`. Keeps the agreed hostname (#10) and leaves the certificate, its validation and the ALB record entirely in PMO's account. Prod uses its own delegated zone at product Phase 5 |
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
| API and web host ports configurable: `PMO_API_PORT` (default 8000) and `PMO_WEB_PORT` (default 3000), set in the Makefile and passed to compose and Playwright | User decision 2026-10-07, refines the row above; another project's dev servers held 8000/3000 and blocked the e2e run. Defaults are unchanged, so CI and the config defaults need nothing. In-container ports stay 8000/3000. The frontend image bakes the API URL, so a new API port needs `make dev-build` |
| `make lint` frontend = eslint + typecheck + format:check; backend = ruff check + ruff format --check + `mypy app` | User decision 2026-10-06; the same gates CI runs. mypy covers `app` only: `app tests` has 57 errors in 8 test files (tech debt) |
| uv pinned to exactly 0.9.18 in the backend Dockerfile (`ghcr.io/astral-sh/uv:0.9.18`) and in CI | User decision 2026-10-07; `uv.lock` is revision 3, written by local uv 0.9.18; II's `uv:0.6` predates that format. Bumped deliberately, like pnpm 12.6.0 |
| CI uses the latest action majors: checkout v7, setup-node v7, upload-artifact v7, setup-uv v10, pnpm/action-setup v6, paths-filter v4 | User decision 2026-10-07; all on the node24 runtime (II's v4-era pins run on node20, being retired). setup-uv publishes no floating major tag, so it is pinned to the release `v10.2.0` (the first CI run failed at "Set up job" on `@v10`) |
| CI e2e runs against the docker compose stack (images built in the job, migrations from the runner, then Playwright) | User decision 2026-10-07; same path as `make dev-build` + `make migrate` + `make test-e2e`, and it exercises the Dockerfiles (the HOSTNAME bug would have been caught) |
| CI keeps II's path filters (backend, frontend; e2e on either, plus compose and the workflow) | User decision 2026-10-07. Skipped jobs still let CI succeed, so the deploy gate passes. Correction 2026-10-07: on a push to a branch other than `main`, paths-filter compares against `main`, not the previous commit, so on `develop` every change not yet on `main` counts and a docs-only push runs the full suite (run 37578611837). Docs-only pushes skip the jobs only once `main` has caught up. The deploy filter compares with the previous commit on the branch |
| Deploy is a `deploy-staging` job inside `ci.yml` that needs every CI job (passed or skipped) and runs on push only | User decision 2026-10-07; same run and commit sha as the checks; only that job gets `id-token: write`. A separate `workflow_run` file would run from the default branch's copy and need the sha checked out by hand |
| Only `develop` → staging is wired in Sprint 0; `main` → production is added when prod infra is applied (product Phase 5) | User decision 2026-10-07; a push to `main` cannot fail on ECS services that do not exist yet |
| Deploy identifiers are repository variables (`vars.AWS_ROLE_ARN`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER_NAME`, `ECS_STAGING_BACKEND_SERVICE`, `ECS_STAGING_FRONTEND_SERVICE`); no repository secrets | User decision 2026-10-07; none are secret with OIDC, and readable values make failures easy to diagnose. GitHub Environments would need GitHub Pro on a private repo. Values come from the Phase 4 Terraform outputs |
| One `.dockerignore` per build context (`backend/`, `frontend/`), tests excluded from images | User decision 2026-10-06; compose builds from `./backend` and `./frontend`, so a root file would not apply |
