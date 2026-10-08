# Test Tracking

## Summary
Counts are taken from the test run output, never estimated (last run 2026-10-08, after sign-in was limited to tenant members with a role: every layer, e2e against the compose stack on ports 8100/3100).

| Layer | Count |
|-------|-------|
| Unit (backend) | 289 |
| Integration (backend, testcontainers pgvector) | 47 |
| Frontend unit (Vitest) | 88 |
| Frontend e2e (Playwright, against the compose stack) | 9 (1 setup + 8) |
| **Total run** | **433** |

## How to run
- Backend unit: `cd backend && uv run pytest tests/unit`
- Backend integration (needs Docker running): `cd backend && uv run pytest tests/integration`
- Frontend unit: `cd frontend && pnpm test`
- Frontend e2e (needs the backend with `LOCAL_AUTH_ENABLED=true` on :8000 and the frontend on :3000): `cd frontend && pnpm test:e2e`
- With make: `make test` (backend unit + integration, frontend unit); `make dev-build`, `make migrate`, then `make test-e2e`. If another dev server holds 8000 or 3000, its answers make the suite fail at `auth.setup.ts`. Move the PMO stack with `make dev-build PMO_API_PORT=8100 PMO_WEB_PORT=3100` and `make test-e2e PMO_API_PORT=8100 PMO_WEB_PORT=3100`
- CI runs the same suites; e2e runs against the compose stack (`.github/workflows/ci.yml`)

## Backend unit tests (`backend/tests/unit/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_access_rule.py` | 14 | `may_use_app` (active and a known role), `assert_may_sign_in` (403, WARNING), `get_current_user` refuses a removed role or disabled account with 401 and a WARNING |
| `test_auth_endpoints.py` | 15 | Register, login, refresh, logout, `/me` (role in the response) |
| `test_auth_schemas.py` | 11 | Auth request/response schemas; `role` required but nullable |
| `test_auth_service.py` | 18 | Password hashing, tokens, register (no role on creation, bootstrap elevation); password login refused without a role or when disabled |
| `test_bootstrap_admins.py` | 6 | Startup bootstrap sweep |
| `test_cost_tracker.py` | 7 | LLM, embedding and transcription cost calculation |
| `test_db_bootstrap.py` | 11 | Bootstrap config from the environment (defaults, overrides, every missing name listed); URL encoding of credentials; random passwords; secret merge keeps other keys; placeholder detection; exit code 2 without settings |
| `test_db_session.py` | 1 | Engine command timeout |
| `test_entitlement_coverage.py` | 20 | Every `/api/v1` route carries a guard or is listed public or self-scoped; placement-id routes carry a placement-scope guard |
| `test_entitlements.py` | 35 | Global vs scoped roles, fail-closed for no role or unknown roles, 404-on-denial, role gate, bootstrap elevation rules |
| `test_health.py` | 1 | Health endpoint |
| `test_llm_factory.py` | 11 | Cached Azure OpenAI clients with timeout |
| `test_memory.py` | 11 | RSS probe and tracemalloc diagnostics |
| `test_processing_ownership.py` | 8 | Takeover order (sweeps, start, re-queues), retry, non-fatal steps, heartbeat loss |
| `test_processing_queue.py` | 27 | Priorities (chat < session < backlog), dedup, dispatch order, workers, stragglers, runner registry |
| `test_processing_status_api.py` | 11 | Queue status route; manager/admin only |
| `test_rate_limiting.py` | 4 | Auth rate limits |
| `test_refresh_tokens.py` | 15 | Refresh token storage, rotation, revocation; refresh refused, every token revoked and a WARNING logged for no role, a disabled account or a missing user |
| `test_security_middleware.py` | 10 | Security headers, CORS lockdown |
| `test_sso_endpoints.py` | 9 | SSO config and callback routes; a refused sign-in answers 403 with the reason and sets no cookie |
| `test_sso_service.py` | 35 | Token exchange, id_token validation, tenant allowlist; guests refused by `acct` (missing claim refused); user found by oid, then email (linked, name taken); no row for an unknown account; bootstrap admin created as `pmo_manager`; full flow refuses no role, disabled or unknown before storing Microsoft tokens |
| `test_user_role_cli.py` | 9 | Role CLI arguments: grant, `none`, `--list`; bad arguments exit 2; a bad address exits 2 without a commit |

## Backend integration tests (`backend/tests/integration/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_auth_api.py` | 11 | Auth flow against Postgres; password login without a role answers 403 with no cookie |
| `test_bootstrap_admins.py` | 3 | Elevation of listed users; a global role is left alone |
| `test_db_bootstrap.py` | 5 | First run creates a non-superuser login that owns the database and `public` schema, can run DDL and use `vector`; a second run keeps the password; rotation invalidates the old password; `run` writes a `DATABASE_URL` that connects and leaves it alone on re-run; an existing login with no URL exits 1 until `--rotate-password` |
| `test_db_command_timeout.py` | 1 | asyncpg command timeout |
| `test_health.py` | 1 | Health endpoint |
| `test_migrations.py` | 2 | `alembic upgrade head` on an empty DB, `alembic check` (no drift), downgrade and re-upgrade |
| `test_placement_scope.py` | 10 | Who can read a placement (each role); denial identical to a missing row; `access_log` rows only for permitted logged reads |
| `test_processing_ownership.py` | 6 | Advisory lock acquire, hold, heartbeat, release |
| `test_sign_in_access.py` | 8 | A role granted by email is linked at the first SSO sign-in; an unknown account leaves no row; change, list, remove-nothing and bad-address cases; removing a role revokes every refresh token; refresh refused once the role is gone; refresh works while it is held |

## Frontend unit tests (`frontend/src/`)
| File | Tests | Covers |
|------|-------|--------|
| `app/auth/callback/microsoft/page.test.tsx` | 8 | Error param, missing code, missing PKCE verifier, code exchange payload and redirect to `/`, exchange failure, a refused sign-in shows the backend's reason, a non-refusal keeps the generic message, back to login |
| `app/layout.test.tsx` | 3 | Metadata name and tagline; toast region mounted; toasts shown |
| `components/admin/AdminView.test.tsx` | 6 | Queue panel for `pmo_manager` and `admin`; no-access message for `sme`, `tech_lead`, `ps` and no role |
| `components/admin/ProcessingStatusPanel.test.tsx` | 6 | Memory formatting; hidden when disabled; idle and busy queues; running jobs by kind, no links; memory diagnostics; request error |
| `components/auth/LoginForm.test.tsx` | 7 | Microsoft button only; progress and error states; no password or sign-up |
| `components/common/DateRangeFilter.test.tsx` | 8 | From/To inputs, clear button, change callbacks |
| `components/common/EmptyState.test.tsx` | 6 | Title, description, link and button actions |
| `components/common/ErrorFallback.test.tsx` | 5 | Default and custom title and description, reset |
| `components/layout/Sidebar.test.tsx` | 3 | Nav for global roles (with Admin) and others (without); risk board at `/` |
| `components/layout/ThemeToggle.test.tsx` | 4 | Light, dark and system options |
| `components/providers/AuthProvider.test.tsx` | 6 | Session restore with role; no-role user stays; signed-in user leaves `/login` for `/`; signed-out visitor stays on `/login`; expiry sends to `/login` |
| `hooks/useProcessingStatus.test.ts` | 3 | No request when disabled; 5 s / 30 s polling; busy flag |
| `hooks/useSSOLogin.test.ts` | 3 | Authority from the server; single-tenant authority; config failure |
| `hooks/useScrollRestore.test.ts` | 3 | Save and restore scroll position per key |
| `lib/api.test.ts` | 6 | One refresh and retry on 401, no refresh loop, session expiry, refresh timeout, shared refresh, no refresh for auth endpoints |
| `lib/pkce.test.ts` | 7 | Verifier and S256 challenge; verifier stored once and cleared |
| `lib/roles.test.ts` | 4 | The five roles; `pmo_manager` and `admin` global; scoped roles and no role not global |

## Frontend e2e tests (`frontend/tests/e2e/`)
| File | Tests | Covers |
|------|-------|--------|
| `auth.setup.ts` | 1 | Registers and signs in with local auth (the user is a bootstrap admin in `docker-compose.yml`, since sign-in needs a role), copies the refresh cookie, lands on the risk board, saves the storage state |
| `auth.spec.ts` | 8 | Login page offers only Microsoft (no password, no sign-up); `/signup` redirects or 404s; signed-in user lands on the risk board, is sent from `/login` to `/`, opens Actions, sees the app name |
