# Test Tracking

## Summary
Counts are taken from the test run output, never estimated (last run 2026-10-06).

| Layer | Count |
|-------|-------|
| Unit (backend) | 241 |
| Integration (backend, testcontainers pgvector) | 33 |
| Frontend | 0 |
| **Total** | **274** |

## How to run
- Backend unit: `cd backend && uv run pytest tests/unit`
- Backend integration (needs Docker running): `cd backend && uv run pytest tests/integration`

## Backend unit tests (`backend/tests/unit/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_auth_endpoints.py` | 15 | Register, login, refresh, logout, `/me` (role in the response) |
| `test_auth_schemas.py` | 11 | Auth request/response schemas; `role` required but nullable |
| `test_auth_service.py` | 17 | Password hashing, tokens, register (no role on creation, bootstrap elevation) |
| `test_bootstrap_admins.py` | 6 | Startup bootstrap sweep |
| `test_cost_tracker.py` | 7 | LLM, embedding and transcription cost calculation |
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
| `test_refresh_tokens.py` | 12 | Refresh token storage, rotation, revocation |
| `test_security_middleware.py` | 10 | Security headers, CORS lockdown |
| `test_sso_endpoints.py` | 8 | SSO config and callback routes |
| `test_sso_service.py` | 26 | Token exchange, id_token validation, multi-tenant allowlist, JIT provisioning with no role |

## Backend integration tests (`backend/tests/integration/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_auth_api.py` | 10 | Auth flow against Postgres |
| `test_bootstrap_admins.py` | 3 | Elevation of listed users; a global role is left alone |
| `test_db_command_timeout.py` | 1 | asyncpg command timeout |
| `test_health.py` | 1 | Health endpoint |
| `test_migrations.py` | 2 | `alembic upgrade head` on an empty DB, `alembic check` (no drift), downgrade and re-upgrade |
| `test_placement_scope.py` | 10 | Who can read a placement (each role); denial identical to a missing row; `access_log` rows only for permitted logged reads |
| `test_processing_ownership.py` | 6 | Advisory lock acquire, hold, heartbeat, release |
