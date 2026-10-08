# Feature Tracking

## Sprint 0: Foundation
| Feature | Files | Status |
|---------|-------|--------|
| Backend skeleton (FastAPI, settings, security headers, CORS, rate limits) | `backend/app/main.py`, `backend/app/config.py`, `backend/app/middleware/security.py`, `backend/app/rate_limiter.py` | Done |
| Sign-in: Entra ID SSO (PKCE) and local auth for dev and CI | `backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py`, `backend/app/services/sso_service.py`, `frontend/src/hooks/useSSOLogin.ts`, `frontend/src/app/auth/callback/microsoft/page.tsx`, `frontend/src/components/providers/AuthProvider.tsx` | Done (backend and frontend) |
| Sign-in for tenant members with a role only: guests refused (id-token `acct`), no row for unknown accounts, role re-checked on refresh and every request, refusal reason shown on the callback page | `backend/app/services/sso_service.py`, `backend/app/utils/entitlements.py`, `backend/app/services/auth_service.py`, `backend/app/dependencies.py`, `frontend/src/app/auth/callback/microsoft/page.tsx` | Done |
| Role grants by email until the Admin page exists (`make user-role`, one-off ECS task) | `backend/app/services/user_roles.py`, `backend/app/cli/user_role.py`, `scripts/user-role.sh`, `infra/modules/environment/admin_cli.tf` | Done |
| Role entitlement with placement scope (404 on denial) and route-coverage check | `backend/app/utils/entitlements.py`, `backend/app/dependencies.py`, `backend/tests/unit/test_entitlement_coverage.py` | Done |
| Access log of consultant-data reads | `backend/app/models/access_log.py`, `backend/app/db/repositories/access_log_repo.py` | Done (writer; no viewer yet) |
| Bootstrap PMO managers from configuration | `backend/app/services/bootstrap_admins.py` | Done |
| Processing queue with priority tiers and runner registry | `backend/app/services/processing_queue.py` | Done (no pipelines registered yet) |
| Processing ownership lock with heartbeat and takeover registry | `backend/app/services/processing_ownership.py` | Done |
| Processing status endpoint | `backend/app/api/v1/processing.py` | Done |
| LLM factory and cost tracker | `backend/app/ai/llm_factory.py`, `backend/app/services/cost_tracker.py` | Done (not used yet) |
| Migration 001: users, register, processing, access log | `backend/alembic/versions/001_create_initial_schema.py` | Done |
| Teams Graph access setup (certificate, app registration, connector app package) | `scripts/teams/`, `teams-app/`, `docs/integrations/TEAMS-GRAPH-SETUP.md` | Done; pending admin approval |
| Frontend skeleton: Next.js 16.3.8 shell with sidebar, header, dark mode, route guard | `frontend/src/app/layout.tsx`, `frontend/src/components/layout/`, `frontend/src/proxy.ts` | Done |
| Role-aware navigation (Admin for `pmo_manager` and `admin` only) | `frontend/src/lib/roles.ts`, `frontend/src/components/layout/Sidebar.tsx` | Done |
| Risk board, Actions and Settings pages | `frontend/src/app/page.tsx`, `frontend/src/app/actions/page.tsx`, `frontend/src/app/settings/page.tsx` | Placeholders (empty states) |
| Admin page with the processing queue | `frontend/src/components/admin/AdminView.tsx`, `frontend/src/components/admin/ProcessingStatusPanel.tsx` | Done |
| Local stack: Docker Compose (PostgreSQL 16 + pgvector, backend, frontend) with health checks and configurable host ports; Makefile targets | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`, `.env.example` | Done |
| CI: path-filtered backend and frontend checks, e2e on the compose stack; staging deploy after the checks pass | `.github/workflows/ci.yml` | Done |
| Infrastructure as code: state bucket, shared stack (VPC, ECR, ECS cluster, GitHub OIDC deploy role) and the staging environment (ALB, RDS, secret, bucket, SES, ECS) | `infra/bootstrap/`, `infra/shared/`, `infra/modules/environment/`, `infra/environments/staging/` | Done (staging applied; production at product Phase 5) |
| Database bootstrap as a one-off ECS task (`pmo_app` login, pgvector, `DATABASE_URL` into the secret) | `backend/app/cli/db_bootstrap.py`, `scripts/db-bootstrap.sh`, `infra/modules/environment/db_bootstrap.tf` | Done (run on staging) |
| PMO's own Azure OpenAI (Sweden Central, Data Zone Standard: gpt-5.4-mini and text-embedding-3-small for staging) | `infra/azure/` | Done (applied) |
| Credential expiry reminders (email 30, 14 and 3 days before) | `infra/shared/expiry_reminders.tf`, `infra/shared/variables.tf` | Done (Teams Graph certificate, Entra SSO staging secret) |
| Entra SSO app registration: single tenant, Web redirect URIs, `acct` claim, per-environment secret into the app secret | `scripts/entra/Register-SsoApp.ps1` | Done (staging) |
| Frontend tooling: Prettier, typecheck and format scripts, pnpm 12 pin | `frontend/package.json`, `frontend/.prettierrc.json`, `frontend/eslint.config.mjs` | Done |

## Sprint 1: Register and Sessions
| Feature | Files | Status |
|---------|-------|--------|
| Transcription settings: AssemblyAI EU endpoint, speech models and prices as configuration (PMO key checked on the EU endpoint 2026-10-08) | `backend/app/config.py`, `backend/app/services/cost_tracker.py`, `.env.example` | Done (the client arrives in Phase 3) |
| Sign-in keeps no Microsoft token (identity scopes only; migration 002 drops the token columns) | `backend/app/services/sso_service.py`, `frontend/src/hooks/useSSOLogin.ts`, `backend/alembic/versions/002_drop_user_ms_tokens.py` | Done |
| Manual staging redeploy of one side (`workflow_dispatch`, `target` backend / frontend / both; checks first) | `.github/workflows/ci.yml` | Done (first manual run 2026-10-08, run 37770017665: frontend only, backend left alone) |
| Placement register: create and edit consultants, clients, projects and placements on the Admin page (placements first, with status filter and search); uniqueness, date and people rules; no delete | `backend/app/services/register_service.py`, `backend/app/api/v1/register.py`, `frontend/src/components/admin/register/` | Done |
| Register CSV import: preview (dry run), then Confirm all-or-nothing; filled cells overwrite, empty cells keep; people by email (existing users with a role); template download | `backend/app/services/register_import.py`, `frontend/src/components/admin/register/ImportTab.tsx` | Done |
| Admin tabs (Register, Import, Processing) with the tab in the URL; the queue polls only on its tab | `frontend/src/components/admin/AdminView.tsx` | Done |
| User list for the admin pages and the people pickers (`GET /users`) | `backend/app/api/v1/users.py` | Done (roles are still changed with `make user-role`) |
