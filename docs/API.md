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
- **No role** (`null`): cannot sign in at all (below), and would read nothing.

**Who may sign in**: an active member of the InformationTech tenant whose user row holds a role.
- `POST /auth/sso/microsoft/callback` answers **403** `{"detail": "Guest accounts cannot sign in to PMO Intelligence."}` for a guest (id-token claim `acct` not `0`, or missing), and **403** `{"detail": "Your account has not been given access to PMO Intelligence. Ask a PMO manager."}` for anyone without an active role. No row is created for an unknown account, except a bootstrap admin (`pmo_manager`).
- `POST /auth/login` (dev and CI only) answers the same 403 for a correct password without a role.
- `POST /auth/refresh` answers **401** `{"detail": "Your session has ended. Please sign in again."}`, clears the cookie and revokes every refresh token of the user, once the role is removed or the account disabled.
- Every authenticated route answers **401** with the same message for such a user, so access ends within the 15-minute access-token life.

## Implemented Endpoints

### Health
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/health` | Public, not rate-limited | `{"status": "healthy", "service": "pmo-intelligence-api"}` |

### Auth
| Method | Path | Auth | Rate limit | Request | Response |
|--------|------|------|-----------|---------|----------|
| POST | `/auth/register` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 3/min | `{email, password (8–128), full_name}` | `201` `UserResponse` |
| POST | `/auth/login` | Public; 403 when `LOCAL_AUTH_ENABLED=false` | 5/min | `{email, password}` | `TokenResponse`; sets the `refresh_token` httpOnly cookie. 403 without a role |
| POST | `/auth/refresh` | `refresh_token` cookie | 10/min | — | `TokenResponse`; rotates the cookie. 401 once the role is removed or the account disabled |
| POST | `/auth/logout` | Bearer | — | — | `{message, revoked_tokens}`; clears the cookie |
| GET | `/auth/me` | Bearer | — | — | `UserResponse` |
| GET | `/auth/sso/microsoft/config` | Public | — | — | `{client_id, tenant_id, authority, redirect_uri}` |
| POST | `/auth/sso/microsoft/callback` | Public | 10/min | `{code, code_verifier, redirect_uri}` | `TokenResponse`; sets the refresh cookie. 403 for a guest or a user without a role |

- **`UserResponse`**: `{id, email, full_name, is_active, auth_provider, role, created_at}`. `role` is one of the roles above, or `null`.
- **`TokenResponse`**: `{access_token, token_type: "bearer"}`. The access token lasts 15 minutes; the refresh cookie lasts 7 days.

### Processing
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/processing/status` | `pmo_manager` or `admin` | `{queue_depth, capacity, running: [{kind, id, started_at, worker}], rss_mib, memory_diagnostics_enabled}` |

### Register
PMO managers and admins edit the register; any other role gets `403 {"detail": "Not authorised for this operation"}`. Updates are `PATCH`: only the fields sent change, and `null` clears a nullable field (a required field sent as `null` is a 422). Nothing is deleted: a placement ends by `status`, a consultant leaves by `status`.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/consultants` | `pmo_manager`, `admin` | — | `ConsultantResponse[]`, by name |
| POST | `/consultants` | `pmo_manager`, `admin` | `{full_name, email?, phone?, skills?, status?}` | `201` `ConsultantResponse`; 409 if the email is taken (any case) |
| PATCH | `/consultants/{consultant_id}` | `pmo_manager`, `admin` | any of the above | `ConsultantResponse` |
| GET | `/clients` | `pmo_manager`, `admin` | — | `ClientResponse[]` |
| POST | `/clients` | `pmo_manager`, `admin` | `{name, industry?}` | `201` `ClientResponse`; 409 if the name exists (ignoring case and spacing) |
| PATCH | `/clients/{client_id}` | `pmo_manager`, `admin` | any of the above | `ClientResponse` |
| GET | `/projects` | `pmo_manager`, `admin` | — | `ProjectResponse[]`, by client then project |
| POST | `/projects` | `pmo_manager`, `admin` | `{client_id, name, client_manager_name?, tech_lead_user_id?, start_date?}` | `201` `ProjectResponse`; 409 if the client already has the name |
| PATCH | `/projects/{project_id}` | `pmo_manager`, `admin` | any of the above | `ProjectResponse` |
| GET | `/placements` | `pmo_manager`, `admin` | — | `PlacementResponse[]`, newest start first |
| POST | `/placements` | `pmo_manager`, `admin` | `{consultant_id, project_id, start_date, expected_end_date?, extension_status?, rate_band?, ps_user_id?, sme_user_id?, status?, ended_reason?}` | `201` `PlacementResponse`; 409 if the consultant already has a placement on the project from that day |
| GET | `/placements/{placement_id}` | placement scope | — | `PlacementResponse`; 404 outside scope |
| PATCH | `/placements/{placement_id}` | `pmo_manager`, `admin` (and placement scope) | any of the above | `PlacementResponse` |
| POST | `/register/import?dry_run=true` | `pmo_manager`, `admin`; 10/min | multipart `file` (`.csv`, at most 1 MB and 1,000 rows) | `ImportResult` (below) |

- **Rules (422)**: `expected_end_date` not before `start_date`; a referenced client, consultant or project must exist; a named person (`tech_lead_user_id`, `ps_user_id`, `sme_user_id`) must be an active user who holds a role, since being named gives that user scoped read of the placement.
- **`PersonRef`**: `{id, full_name, email}`.
- **`ConsultantResponse`**: `{id, full_name, email, phone, skills, status, created_at, updated_at}`; `status` is `bench | placed | left`.
- **`ClientResponse`**: `{id, name, industry, created_at, updated_at}`.
- **`ProjectResponse`**: `{id, client_id, client_name, name, client_manager_name, tech_lead: PersonRef | null, start_date, created_at, updated_at}`.
- **`PlacementResponse`**: `{id, consultant: {id, full_name, email}, client: {id, name}, project: {id, name}, start_date, expected_end_date, extension_status, rate_band, status, ended_reason, ps, sme, tech_lead, created_at, updated_at}`; `extension_status` is `not_due | due | requested | confirmed | declined`, `status` is `active | ended | terminated`, and `ps`, `sme`, `tech_lead` are `PersonRef | null`.

**CSV import** (`POST /register/import`):
- **Columns** (all twelve in the header, in any order, case-insensitive): `consultant_full_name, consultant_email, client_name, project_name, client_manager_name, tech_lead_email, ps_email, sme_email, start_date, expected_end_date, extension_status, rate_band`. Required in every row: `consultant_full_name`, `client_name`, `project_name`, `start_date`.
- **File**: UTF-8, with or without a BOM (Excel's "CSV UTF-8"); dates `YYYY-MM-DD` or `DD/MM/YYYY`. A problem with the file itself (not `.csv`, too large, not UTF-8, missing or unknown columns, no rows) answers **422** with the reason.
- **Matching**: clients on their normalised name; consultants on email, else on full name (a consultant entered without an email gains it); projects on (client, name); placements on (consultant, project, start date). Rows apply in file order, so one row's new client is found by the next.
- **Updates**: a filled cell overwrites the stored value; an empty cell keeps it. Re-importing the same file changes nothing.
- **People** are named by email and must be active users with a role; the import never creates a user. A user whose role differs from the column (a `pmo_manager` as PS) is a warning, not an error.
- **All or nothing**: `dry_run=true` (the default) never writes. `dry_run=false` writes every row, or none when any row has an error. The answer is **200** either way; `applied` says whether it wrote.
- **`ImportResult`**: `{dry_run, applied, summary: {rows, created, updated, unchanged, errors}, rows: [{row, outcome, consultant, client, project, changes, warnings, errors}]}`. `row` is the line number (the header is line 1); `outcome` is `create` (a new placement), `update`, `unchanged` or `error`.

### Users
| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/users` | `pmo_manager`, `admin` | `[{id, email, full_name, role, is_active, signed_in_with_microsoft}]`, by email; no tokens, no Entra ids |

## Common Response Formats
### Error Response
```json
{
  "detail": "Error message"
}
```
A rate-limited request answers `429`.
