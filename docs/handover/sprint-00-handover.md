# Sprint 00 Handover Document

**Sprint Duration**: 2026-10-06 - 2026-10-08 (planned 2026-10-07 – 2026-10-20; finished early)
**Sprint Objective**: Bootstrap the repository: the stack copied from Interview Intelligence (queue, ownership lock, LLM factory, auth, CI, Docker, Terraform), SSO sign-in with roles, an empty dashboard deployed to staging, the Graph app registration created and the Teams permission request submitted.
**Audit Status**: PASSED — see `docs/tracking/SPRINT-AUDIT.md`

> **GATE**: This handover can ONLY be created AFTER the sprint audit is complete.

**Exit gate (PRD Phase 0): met 2026-10-08.**
- The staging URL `https://pmo-intelligence-staging.itcapp.ai` signs in with Microsoft SSO. Abhishek is `pmo_manager`, re-checked on the final build.
- CI is green on `develop` (run 37748446898: backend, frontend, e2e and the staging deploy).
- The Teams app "PMO Intelligence" is approved and published (1.0.0). No ticket number was issued; the approval meets the gate's intent (user decision 2026-10-08).

## 1. What Was Achieved
- **Backend skeleton** (`backend/app/`): FastAPI layered routes → services → repositories → models; settings (`config.py`); security headers, CORS and rate limits (`middleware/`, `rate_limiter.py`); health, auth and processing-status routes (`api/v1/`).
- **Processing core** copied and made generic: priority queue with a runner registry (`services/processing_queue.py`) and the Postgres advisory ownership lock with registered takeover steps (`services/processing_ownership.py`); LLM factory with a finite timeout (`ai/llm_factory.py`); cost tracker (`services/cost_tracker.py`).
- **Data model**: migration 001 (`alembic/versions/001_create_initial_schema.py`): users, refresh tokens, consultants, clients, projects, placements, processing jobs and costs, access log; pgvector; CHECK constraints from `models/enums.py`.
- **Auth and access**:
  - Entra ID SSO with PKCE, the code redeemed by the backend (`services/sso_service.py`).
  - Single-tenant app registration "PMO Intelligence" (`scripts/entra/Register-SsoApp.ps1`).
  - **Only members of the tenant who hold a role can sign in**: guests are refused by the id-token `acct` claim (fail closed); no user row is created at sign-in except for bootstrap admins; the role is re-checked on refresh and on every request (`utils/entitlements.py`, `services/auth_service.py`, `dependencies.py`).
  - Roles are granted by email with `make user-role` (`services/user_roles.py`, `cli/user_role.py`, `scripts/user-role.sh`).
  - Placement scope answers 404 on denial, with an `access_log` writer and a route-coverage test (`tests/unit/test_entitlement_coverage.py`).
- **Frontend skeleton** (`frontend/`): Next.js 16.3.8, React 19.2, shadcn/ui, SWR, dark mode; Microsoft-only login with PKCE; the callback page shows the backend's refusal reason; a route guard (`src/proxy.ts`); sidebar with Risk board, Actions, Admin (global roles only) and Settings; the Admin page shows the processing queue; Prettier, typecheck and format scripts; pnpm 12.
- **Local development** (`docker-compose.yml`, `Makefile`, both Dockerfiles, `.env.example`): pgvector, backend and frontend with health checks and configurable host ports; `make dev-build`, `migrate`, `test`, `test-e2e`, `lint`, `format`, `db-bootstrap`, `user-role`.
- **CI/CD** (`.github/workflows/ci.yml`): path-filtered backend checks (ruff, mypy strict, unit, integration) and frontend checks (eslint, typecheck, Prettier, Vitest, build); Playwright e2e on the compose stack; staging deploy over OIDC after every check passes, only for the changed side.
- **AWS infrastructure** in its own account (ITC Sandbox PD Intelligence, `260172548683`, eu-west-2), all Terraform with remote state:
  - `infra/bootstrap/`: the state bucket, 7 resources.
  - `infra/shared/`: VPC, ECR, ECS cluster, GitHub OIDC deploy role, deny-deletion policy and credential expiry reminders; 34 resources.
  - `infra/modules/environment/` applied as `infra/environments/staging/`: delegated hosted zone, certificate, ALB, RDS PostgreSQL 16, app secret, media bucket, SES identity, ECS services, database bootstrap and admin-cli task definitions; 61 resources.
- **Database bootstrap** as a one-off ECS task (`backend/app/cli/db_bootstrap.py`, `make db-bootstrap`): the `pmo_app` login owns the database; its URL went straight into the secret.
- **Azure OpenAI** for PMO (`infra/azure/`): `rg-pmo-intelligence-swc` and `oai-pmo-intelligence-swc` in Sweden Central, Data Zone Standard deployments `gpt-5.4-mini-staging` and `text-embedding-3-small-staging`; endpoint and key in the staging secret.
- **Credential expiry reminders** (`infra/shared/expiry_reminders.tf`): emails 30, 14 and 3 days before the Teams Graph certificate (2027-10-06) and the Entra SSO staging secret (2027-10-08) expire.
- **Teams Graph access** (`scripts/teams/`, `teams-app/`, `docs/integrations/TEAMS-GRAPH-SETUP.md`): certificate, "PMO Intelligence Graph" app registration with app-only sign-in verified, RSC Teams app package; the Teams app is approved and published.
- **Docs**: PRD, ARCHITECTURE, API, DEPLOYMENT, README, Teams setup, planning and tracking, the sprint audit.
- **Tests**: 289 backend unit + 47 integration + 88 frontend unit + 9 e2e = **433**, all passing; `make lint` clean.

## 2. What Was NOT Achieved
All Sprint 0 tasks are done. These items remain, all in `docs/planning/BACKLOG.md`:
- **Teams app availability** is "everyone" (org-wide default, including guests and external users). It is to be narrowed to the PMO team by the tenant admin (agreed 2026-10-08, not yet done).
- **Chat RSC state and the A5 read test** (the app added to a test chat, `verify_chat_access.py`) are not done. They need a Teams or Global admin and a test chat, and are due before Phase 3. The app is installed for no one.
- **No ticket number** exists for the Teams request: none was issued. The approval itself closed the item.
- **A no-role member's refusal was not tried on staging by a real person.** It is covered by unit and integration tests, and the deployed build was checked with a role holder.
- **Production** is not applied. It is planned at product Phase 5.

## 3. Decisions Made
The full list, with every user decision, is the Decisions Log in `docs/planning/CURRENT-SPRINT.md`. The decisions that shape later sprints:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Fully separate AWS account (ITC Sandbox PD Intelligence, `260172548683`); the only outside link is one NS record delegating `pmo-intelligence-staging.itcapp.ai` | No blast radius shared with Interview Intelligence; PMO owns its VPC, RDS, ALB, OIDC provider and state | Own databases on II's shared RDS instance; own RDS in the shared default VPC |
| Terraform: `infra/shared/` + `infra/modules/environment/` + `infra/environments/<env>/`, S3 state with native locking | A staging apply cannot touch prod; no copy-paste between environments | One `infra/` with prod behind a variable; local state like II |
| ECS tasks in public subnets with a public IPv4, no NAT; RDS private; S3 gateway endpoint only | Egress to Azure, AssemblyAI and Entra at a fraction of NAT's cost; tasks admit only the ALB | NAT gateway; interface endpoints |
| RDS master password managed by RDS; the app connects as `pmo_app`, whose URL only the bootstrap task writes | No password in state or seen by a person | II's Terraform-generated password |
| Azure OpenAI in PMO's own resource group, Sweden Central, **Data Zone Standard** | Workers' transcripts processed only in the EU data zone; cost tracked separately | II's East US resource; UK South Global Standard |
| Entra SSO: **single tenant**, one app "PMO Intelligence" for all environments, one 12-month client secret per environment, Web redirect URIs, assignment **not** required | Every user is in the InformationTech tenant; assignment required forces admin consent | Multi-tenant + allowlist; one app per environment; assignment required with admin consent |
| **Sign-in only for tenant members with a role**: guests refused by `acct` (fail closed), no row at sign-in except bootstrap admins, role re-checked on refresh and each request | 595 guest accounts sit beside 110 members in the tenant; access by default is none | Leave everyone able to sign in with no role; the `idp` claim; record no-role users; check at sign-in only |
| Roles granted by a one-off ECS CLI (`make user-role`) until the Admin "Users and roles" page exists (Sprint 1) | Gives access now without building the page in Sprint 0 | Build the page now; bootstrap list only |
| Credential expiry reminders by EventBridge Scheduler and SNS email from a `credential_expiries` map | No extra Graph credential to watch Entra | A daily checker reading Entra |
| Deploy only after CI passes, `develop` → staging only; identifiers as repository variables | II deploys even when CI fails; nothing here is secret with OIDC | A separate `workflow_run` deploy; GitHub Environments (needs Pro) |
| UK only, no branch column | User decision (#9) | Model branch from day one |
| Teams: one group chat per consultant; RSC `ChatMessage.Read.Chat`, `Chat.Read.All` as an ungranted fallback | Least privilege, visible to chat members | Application permission first; a service account |
| Exit gate met by the Teams app's approval rather than a ticket number | None was issued; the approval is what the ticket would have tracked | Hold the gate open for a ticket |

## 4. Files Created / Modified
Generated from `git diff --name-status e7b2137 HEAD` at `7ab4ba5`. The initial commit `e7b2137` added 14 doc scaffold files (PRD, architecture, API, planning and tracking docs, the two diagrams, the handover template, `.gitignore`); those modified since are marked M. The closing commit also modifies `README.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/planning/{BACKLOG,ROADMAP,CURRENT-SPRINT}.md` and `docs/tracking/{FEATURES,SPRINT-AUDIT}.md`, and adds this handover.

| Area | Files (all added unless marked M) | Description |
|------|-----------------------------------|-------------|
| `backend/app/` (49) | `__init__.py`, `ai/__init__.py`, `ai/llm_factory.py`, `api/__init__.py`, `api/router.py`, `api/v1/__init__.py`, `api/v1/auth.py`, `api/v1/health.py`, `api/v1/processing.py`, `cli/__init__.py`, `cli/db_bootstrap.py`, `cli/user_role.py`, `config.py`, `db/__init__.py`, `db/repositories/__init__.py`, `db/repositories/access_log_repo.py`, `db/repositories/base.py`, `db/repositories/user_repo.py`, `db/session.py`, `dependencies.py`, `main.py`, `middleware/__init__.py`, `middleware/security.py`, `models/__init__.py`, `models/access_log.py`, `models/base.py`, `models/enums.py`, `models/processing_cost.py`, `models/processing_job.py`, `models/refresh_token.py`, `models/register.py`, `models/user.py`, `rate_limiter.py`, `schemas/__init__.py`, `schemas/auth.py`, `schemas/common.py`, `schemas/processing_status.py`, `services/__init__.py`, `services/auth_service.py`, `services/bootstrap_admins.py`, `services/cost_tracker.py`, `services/processing_ownership.py`, `services/processing_queue.py`, `services/sso_service.py`, `services/user_roles.py`, `utils/__init__.py`, `utils/entitlements.py`, `utils/exceptions.py`, `utils/memory.py` | Backend application: FastAPI app, settings, auth and SSO (members with a role only), entitlements, processing queue and ownership lock, LLM factory, cost tracker, models, repositories, role CLI and database bootstrap |
| `backend/alembic` (4) | `.ini`, `/env.py`, `/script.py.mako`, `/versions/001_create_initial_schema.py` | Async Alembic setup and migration 001 |
| `backend/tests/unit/` (24) | `__init__.py`, `conftest.py`, `test_access_rule.py`, `test_auth_endpoints.py`, `test_auth_schemas.py`, `test_auth_service.py`, `test_bootstrap_admins.py`, `test_cost_tracker.py`, `test_db_bootstrap.py`, `test_db_session.py`, `test_entitlement_coverage.py`, `test_entitlements.py`, `test_health.py`, `test_llm_factory.py`, `test_memory.py`, `test_processing_ownership.py`, `test_processing_queue.py`, `test_processing_status_api.py`, `test_rate_limiting.py`, `test_refresh_tokens.py`, `test_security_middleware.py`, `test_sso_endpoints.py`, `test_sso_service.py`, `test_user_role_cli.py` | Backend unit tests (289) |
| `backend/tests/integration/` (11) | `__init__.py`, `conftest.py`, `test_auth_api.py`, `test_bootstrap_admins.py`, `test_db_bootstrap.py`, `test_db_command_timeout.py`, `test_health.py`, `test_migrations.py`, `test_placement_scope.py`, `test_processing_ownership.py`, `test_sign_in_access.py` | Backend integration tests against testcontainers PostgreSQL (47) |
| `backend/tests/` (1) | `conftest.py` | Shared test fixtures |
| `backend/` (5) | `.dockerignore`, `.python-version`, `Dockerfile`, `pyproject.toml`, `uv.lock` | Backend packaging, image and tooling: pyproject, uv lock, Dockerfile, ignore files |
| `frontend/src/app/` (15) | `actions/page.tsx`, `admin/error.tsx`, `admin/page.tsx`, `api/health/route.ts`, `auth/callback/microsoft/page.test.tsx`, `auth/callback/microsoft/page.tsx`, `error.tsx`, `favicon.ico`, `global-error.tsx`, `globals.css`, `layout.test.tsx`, `layout.tsx`, `login/page.tsx`, `page.tsx`, `settings/page.tsx` | Next.js App Router pages: risk board, actions, settings, admin, login, SSO callback, health route |
| `frontend/src/components/` (43) | `admin/AdminView.test.tsx`, `admin/AdminView.tsx`, `admin/ProcessingStatusPanel.test.tsx`, `admin/ProcessingStatusPanel.tsx`, `auth/LoginForm.test.tsx`, `auth/LoginForm.tsx`, `common/DateRangeFilter.test.tsx`, `common/DateRangeFilter.tsx`, `common/EmptyState.test.tsx`, `common/EmptyState.tsx`, `common/ErrorFallback.test.tsx`, `common/ErrorFallback.tsx`, `common/LoadingSpinner.tsx`, `common/Pagination.tsx`, `layout/Header.tsx`, `layout/MainLayout.tsx`, `layout/Sidebar.test.tsx`, `layout/Sidebar.tsx`, `layout/ThemeToggle.test.tsx`, `layout/ThemeToggle.tsx`, `providers/AuthProvider.test.tsx`, `providers/AuthProvider.tsx`, `providers/SWRProvider.tsx`, `theme-provider.tsx`, `ui/badge.tsx`, `ui/button.tsx`, `ui/calendar.tsx`, `ui/card.tsx`, `ui/chart.tsx`, `ui/checkbox.tsx`, `ui/dialog.tsx`, `ui/dropdown-menu.tsx`, `ui/form.tsx`, `ui/input.tsx`, `ui/label.tsx`, `ui/select.tsx`, `ui/separator.tsx`, `ui/skeleton.tsx`, `ui/sonner.tsx`, `ui/switch.tsx`, `ui/table.tsx`, `ui/tabs.tsx`, `ui/textarea.tsx` | Layout shell, auth, admin queue panel, common components and the shadcn/ui set |
| `frontend/src/hooks/` (7) | `useDebounce.ts`, `useProcessingStatus.test.ts`, `useProcessingStatus.ts`, `useSSOLogin.test.ts`, `useSSOLogin.ts`, `useScrollRestore.test.ts`, `useScrollRestore.ts` | SWR and auth hooks |
| `frontend/src/lib/` (10) | `api.test.ts`, `api.ts`, `auth-token.ts`, `constants.ts`, `download.ts`, `pkce.test.ts`, `pkce.ts`, `roles.test.ts`, `roles.ts`, `utils.ts` | API client, token store, PKCE, roles, constants, helpers |
| `frontend/src/` (5) | `proxy.ts`, `test/setup.ts`, `types/api.ts`, `types/auth.ts`, `types/processing.ts` | Route guard, test setup, types |
| `frontend/tests/` (3) | `e2e/auth.setup.ts`, `e2e/auth.spec.ts`, `e2e/fixtures/.gitkeep` | Playwright e2e (setup and auth specs) |
| `frontend/` (15) | `.dockerignore`, `.gitignore`, `.prettierignore`, `.prettierrc.json`, `Dockerfile`, `components.json`, `eslint.config.mjs`, `next.config.ts`, `package.json`, `playwright.config.ts`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `postcss.config.mjs`, `tsconfig.json`, `vitest.config.mts` | Frontend packaging, image and tooling: package.json, pnpm lock and workspace, Dockerfile, ESLint, Prettier, Vitest, Playwright, Next config |
| `infra/bootstrap/` (6) | `.terraform.lock.hcl`, `backend.tf`, `main.tf`, `outputs.tf`, `variables.tf`, `versions.tf` | Terraform state bucket |
| `infra/shared/` (10) | `.terraform.lock.hcl`, `ecr.tf`, `ecs.tf`, `expiry_reminders.tf`, `github_oidc.tf`, `network.tf`, `outputs.tf`, `protection.tf`, `variables.tf`, `versions.tf` | Terraform shared stack: VPC, ECR, ECS cluster, GitHub OIDC deploy role, deny-deletion policy, credential expiry reminders |
| `infra/modules/` (16) | `environment/admin_cli.tf`, `environment/alb.tf`, `environment/db_bootstrap.tf`, `environment/dns.tf`, `environment/ecs.tf`, `environment/iam.tf`, `environment/logs.tf`, `environment/main.tf`, `environment/outputs.tf`, `environment/rds.tf`, `environment/secrets.tf`, `environment/security_groups.tf`, `environment/ses.tf`, `environment/storage.tf`, `environment/variables.tf`, `environment/versions.tf` | Terraform environment module: DNS, certificate, ALB, security groups, RDS, secret, bucket, SES, logs, IAM, ECS services, database bootstrap and admin-cli task definitions |
| `infra/environments/` (6) | `staging/.terraform.lock.hcl`, `staging/main.tf`, `staging/outputs.tf`, `staging/terraform.tfvars.example`, `staging/variables.tf`, `staging/versions.tf` | Terraform staging environment |
| `infra/azure/` (5) | `.terraform.lock.hcl`, `main.tf`, `outputs.tf`, `variables.tf`, `versions.tf` | Terraform for PMO's Azure OpenAI resource group, resource and deployments |
| `scripts/teams/` (3) | `New-GraphCertificate.ps1`, `Register-GraphApp.ps1`, `verify_chat_access.py` | Teams Graph certificate, app registration and chat-access check |
| `scripts/entra/` (1) | `Register-SsoApp.ps1` | Entra SSO app registration |
| `scripts/` (2) | `db-bootstrap.sh`, `user-role.sh` | One-off ECS task runners: database bootstrap, role grants |
| `teams-app/` (4) | `build_package.py`, `color.png`, `manifest.template.json`, `outline.png` | Teams connector app package (RSC manifest) and its builder |
| `.github/` (1) | `workflows/ci.yml` | CI: checks, e2e and the staging deploy |
| `docs/` (9) | `API.md (M)`, `ARCHITECTURE.md (M)`, `DEPLOYMENT.md`, `integrations/TEAMS-GRAPH-SETUP.md`, `planning/BACKLOG.md (M)`, `planning/CURRENT-SPRINT.md (M)`, `tracking/CHANGELOG.md (M)`, `tracking/FEATURES.md (M)`, `tracking/TESTS.md (M)` | Product and engineering docs: PRD, architecture, API, deployment, Teams setup, planning, tracking |
| repository root (5) | `.env.example`, `.gitignore (M)`, `Makefile`, `README.md`, `docker-compose.yml` | Repository root: compose stack, Makefile, env example, README, ignore rules |

**260 files**: 252 added, 8 modified (since the initial docs commit `e7b2137`).

## 5. Environment Changes
- **New dependencies**:
  - Backend: as Interview Intelligence, pruned with `uv lock` (dropped the second LLM SDK, fpdf2, weasyprint, rapidfuzz, markdown, xlsxwriter); uv pinned to 0.9.18 (lock revision 3).
  - Frontend: Next.js 16.3.8 (clears CVE-2026-64642 and the other 16.0.0–16.2.10 CVEs), Prettier 3.9.9 with `eslint-config-prettier`; dropped date-fns, react-markdown, remark-gfm and @tailwindcss/typography; pnpm 12.6.0 (`packageManager`), Node 22 or later.
  - Tools: GNU make on Windows (`winget install ezwinports.make`); Terraform 1.10+ with the AWS provider `~> 6.0` and azurerm.
- **New environment variables**: everything `backend/app/config.py` reads is in `.env.example`. The ones that matter for PMO:
  - `BOOTSTRAP_ADMIN_EMAILS`: raised to `pmo_manager`. Staging: Abhishek, in the git-ignored `infra/environments/staging/terraform.tfvars`. Compose: the e2e user.
  - `LOCAL_AUTH_ENABLED`: dev and CI only.
  - `AZURE_ALLOWED_TENANT_IDS`: empty, single tenant.
  - `PROCESSING_CONCURRENCY`.
  - `PMO_API_PORT` / `PMO_WEB_PORT`: make and compose only.
- **Configuration changes**:
  - Staging app secret `pmo-intelligence/staging/app` holds `DATABASE_URL` (bootstrap), `SECRET_KEY`, the Azure OpenAI values, the AssemblyAI key and the Entra SSO values; `AZURE_ALLOWED_TENANT_IDS` is empty.
  - GitHub repository variables: `AWS_ROLE_ARN`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER_NAME`, `ECS_STAGING_BACKEND_SERVICE`, `ECS_STAGING_FRONTEND_SERVICE`.
- **Infrastructure changes**:
  - AWS `260172548683`: bootstrap 7, shared 34, staging 61 resources.
  - Azure: 5 resources, plus a permanent policy exemption scoped to `rg-pmo-intelligence-swc`. The 2-hour subscription waiver used for the first creation was deleted.
  - Entra: "PMO Intelligence" (SSO, `ac99fe5f-a3bb-4299-afdc-0da9bdeab113`, secret `staging` to 2027-10-08, optional claim `acct`) and "PMO Intelligence Graph" (`d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3`, certificate to 2027-10-06).
  - Teams: app "PMO Intelligence" 1.0.0 published.
  - DNS: NS record for `pmo-intelligence-staging.itcapp.ai` in the `itcapp.ai` zone (account `430006376054`).

## 6. Known Issues / Bugs
- **Medium (security)**: the backend stores every user's Microsoft access and refresh tokens in `users.ms_access_token` / `ms_refresh_token` at each sign-in. This is copied Interview Intelligence code, and nothing in PMO uses the tokens (`refresh_microsoft_token` has no callers). PMO reads Teams with its own app credential, so this stores sensitive data with no purpose. **BACKLOG**: stop storing them and drop the columns.
- **Medium (security)**: the Teams app is available to everyone, including guests and external users, so anyone can add it to a chat and grant it read access there. Narrowing is with the admin (BACKLOG).
- **Low**: the backend's `migration` container runs with debug on and echoes SQL into its log group (BACKLOG Tech Debt; the fix redeploys the backend).
- **Low**: mypy strict covers `app` only; `app tests` has 57 errors in 8 test files (BACKLOG Tech Debt).
- **Low**: no branch protection on `main`/`develop` (needs GitHub Pro; BACKLOG).
- **Low**: the integration fixtures replace `get_current_user`, so the per-request role check is covered by unit tests (`test_access_rule.py`), not against Postgres.
- **Low**: CI rebuilds only the side that changed, and has no manual redeploy trigger. A hand-built image is the only way to rebuild an unchanged side; follow the DEPLOYMENT.md steps and the infra and tooling rules.

## 7. Learnings
### What Went Well
- The plan-first, approve-then-apply flow on every Terraform and Azure change: no surprise in any apply, and every plan matched what was applied.
- The pre-commit hook caught a tooling reference before it reached git.
- Running the e2e suite on the compose stack in CI exercises the real images.
- Separate infrastructure from day one made every staging change low-risk.

### What Didn't Go Well
- Two staging sign-in failures that a check would have caught: the hand-built frontend image baked a Windows path as its API URL, and "assignment required" was offered without its admin-consent consequence.
- Docs lagged their phases: ROADMAP, FEATURES and the DEPLOYMENT status line were only brought up to date by the audit.
- A first-run-only test of a PowerShell script hid a Windows PowerShell 5.1 array behaviour.

### Rules Added / Updated
21 rules in the local project rules (git workflow, sprint workflow, security, and a new infrastructure and tooling file), each with a Learnings Log line. The list is in `docs/tracking/SPRINT-AUDIT.md`, "Rules Added This Sprint".

## 8. Post-Sprint Audit Findings
**Findings count**: 21 (15 recorded and fixed during the sprint, 6 found and fixed by the audit)
**Rules added**: 21

| What was wrong | Root cause | Rule added/updated |
|---------------|-----------|-------------------|
| CI pinned a nonexistent `setup-uv@v10` tag | Assumed floating major tags | Verify every `uses:` ref before pushing |
| Docs misstated which pushes skip CI | Comparison base not checked | State the comparison base for path-filtered CI |
| e2e failed on ports held by another project | Fixed ports assumed free | Check ports; configurable `PMO_API_PORT`/`PMO_WEB_PORT` |
| A saved plan file showed as untracked | Narrow ignore rule | `tfplan*` naming and `git status` after plans |
| First deploy failed at OIDC | Trust condition copied without reading the subject | Read the OIDC subject first |
| ECR `docker login` failed on Windows | Credential store limitation | Temporary `DOCKER_CONFIG` |
| `make db-bootstrap` failed on a path with a space | Unquoted script path | Call scripts through `bash` |
| Azure apply blocked by MFA and a policy | Requirements not read first | Read policies and the MFA claim before planning |
| An Azure scope became a Windows path | Git Bash path conversion | `MSYS_NO_PATHCONV=1` |
| Session State was stale for the next session | Written before the actions | Refresh after commit, push and apply |
| Frontend image baked `C:/Program Files/Git/api/v1` | Git Bash rewrote the build argument | Grep hand-built bundles; re-check old steps after a new rule |
| "Need admin approval" at sign-in | Assignment required forces admin consent; not stated | State identity settings' side effects before offering them |
| SSO script re-run matched two apps | PowerShell 5.1 `ConvertFrom-Json` | Run scripts twice; parentheses around `ConvertFrom-Json` |
| Admin task echoed SQL | Debug default; copied environment | `APP_DEBUG=false` on backend containers |
| Commit blocked for naming the local rules' path | Wrote about the rules' location | Say "local rules" in committed docs |
| ROADMAP unchecked | Ticks left for sprint end | Tick with the phase |
| DEPLOYMENT status stale | Not in phase doc lists | Status lines in every phase; counts from state |
| FEATURES missed Phases 3–5 | Treated as product-only | FEATURES covers operator features |
| BACKLOG pointed to a missing section | Referenced by number | Reference by heading after checking |
| Three `ci:` commits outside the type list | List not checked | `ci` type added; check before committing |
| README lacked two make targets | Documented in DEPLOYMENT only | README row with every new target |

## 9. Next Sprint Recommendations
### Priority 1 (Must Do)
- **Plan Sprint 1 (PRD Phase 1, Register and sessions)** with `/sprint-start`. First answer the open BACKLOG questions it needs:
  - #2: where the PMO call recordings live (S3 scanner, or upload and URL first).
  - #3: system of record for placements.
  - #5: what an SME may see.
  - #6: the consultant notice.
  - #7: the starting weights (needed by Phase 2, worth starting).
- **Placement register**: admin pages and the CSV import (PRD Phase 1).
- **Admin "Users and roles" page**, replacing `make user-role` for everyday use, with the access-log view in mind (PRD Phase 4).
- **Session ingestion** (upload, URL, S3 folder), transcription and the session pipeline toward the Phase 1 exit gate: three real PMO calls processed end to end.

### Priority 2 (Should Do)
- Stop storing users' Microsoft tokens and drop the two columns (migration 002).
- Get the Teams app's availability narrowed to the PMO team (admin).
- `APP_DEBUG=false` on the migration container, or a production-safe default in `config.py`.

### Priority 3 (Nice to Have)
- Chat RSC check and the A5 read test well before Phase 3.
- mypy strict over the tests.
- A manual CI redeploy trigger (`workflow_dispatch` with a backend/frontend choice), so no image is ever built by hand again.
- GitHub Pro decision for branch protection.
