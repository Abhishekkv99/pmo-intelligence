# Feature Tracking

## Sprint 0: Foundation
| Feature | Files | Status |
|---------|-------|--------|
| Backend skeleton (FastAPI, settings, security headers, CORS, rate limits) | `backend/app/main.py`, `backend/app/config.py`, `backend/app/middleware/security.py`, `backend/app/rate_limiter.py` | Done |
| Sign-in: Entra ID SSO (PKCE) and local auth for dev and CI | `backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py`, `backend/app/services/sso_service.py`, `frontend/src/hooks/useSSOLogin.ts`, `frontend/src/app/auth/callback/microsoft/page.tsx`, `frontend/src/components/providers/AuthProvider.tsx` | Done (backend and frontend) |
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
| Frontend tooling: Prettier, typecheck and format scripts, pnpm 12 pin | `frontend/package.json`, `frontend/.prettierrc.json`, `frontend/eslint.config.mjs` | Done |
