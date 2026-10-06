# API Documentation

## Base URL
- Development: `http://localhost:8000/api/v1`
- Staging: `https://pmo-intelligence-staging.itcapp.ai/api/v1`
- Production: `https://pmo-intelligence.itcapp.ai/api/v1`

All routes live under `/api/v1`. Authenticated routes take `Authorization: Bearer <access token>`.

## Access rules
Applied on the server for every route; the route-coverage test (`backend/tests/unit/test_entitlement_coverage.py`) fails the build for a route without a guard.

| Guard | Used for | Denied response |
|-------|----------|-----------------|
| `require_roles(...)` | Operations that address no placement (admin, queue status) | `403 {"detail": "Not authorised for this operation"}` |
| `require_placement_scope` | Routes addressed by a placement id | `404`, identical to a missing placement |
| `require_logged_placement_scope` | Routes that show a consultant's data; also writes an `access_log` row | `404`, identical to a missing placement |

**Roles** are `pmo_manager`, `sme`, `tech_lead`, `ps` and `admin`, defined in `backend/app/models/enums.py`.
- **Global roles** (`pmo_manager`, `admin`) read every placement.
- **Other roles** read only the placements that name them, as PS, SME, or the project's tech lead.
- **No role** (`null`), the state of a new account, reads nothing.

## Implemented Endpoints

### Health
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/health` | Public, not rate-limited | `{"status": "healthy", "service": "pmo-intelligence-api"}` |

### Auth
| Method | Path | Auth | Rate limit | Request | Response |
|--------|------|------|-----------|---------|----------|
| POST | `/auth/register` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 3/min | `{email, password (8–128), full_name}` | `201` `UserResponse` |
| POST | `/auth/login` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 5/min | `{email, password}` | `TokenResponse`; sets the `refresh_token` httpOnly cookie |
| POST | `/auth/refresh` | `refresh_token` cookie | 10/min | — | `TokenResponse`; rotates the cookie |
| POST | `/auth/logout` | Bearer | — | — | `{message, revoked_tokens}`; clears the cookie |
| GET | `/auth/me` | Bearer | — | — | `UserResponse` |
| GET | `/auth/sso/microsoft/config` | Public | — | — | `{client_id, tenant_id, authority, redirect_uri}` |
| POST | `/auth/sso/microsoft/callback` | Public | 10/min | `{code, code_verifier, redirect_uri}` | `TokenResponse`; sets the refresh cookie |

- **`UserResponse`**: `{id, email, full_name, is_active, auth_provider, role, created_at}`. `role` is one of the roles above, or `null`.
- **`TokenResponse`**: `{access_token, token_type: "bearer"}`. The access token lasts 15 minutes; the refresh cookie lasts 7 days.

### Processing
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/processing/status` | `pmo_manager` or `admin` | `{queue_depth, capacity, running: [{kind, id, started_at, worker}], rss_mib, memory_diagnostics_enabled}` |

## Common Response Formats
### Error Response
```json
{
  "detail": "Error message"
}
```
A rate-limited request answers `429`.
