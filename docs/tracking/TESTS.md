# Test Tracking

## Summary
Counts are taken from the test run output, never estimated. Last run 2026-10-08 (Sprint 1 Phase 3, ingestion services): backend unit (integration from the migration 003 run, no database change since); frontend unit and e2e from the Phase 2 run (no frontend change since); e2e against the compose stack on ports 8100/3100.

| Layer | Count |
|-------|-------|
| Unit (backend) | 468 |
| Integration (backend, testcontainers pgvector) | 100 |
| Frontend unit (Vitest) | 113 |
| Frontend e2e (Playwright, against the compose stack) | 12 (1 setup + 11) |
| **Total** | **693** |

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
| `test_assemblyai_client.py` | 6 | Polls a submitted transcript until completed and returns utterances in ms; the EU base URL, key, models and the 2–4 speaker range come from settings; a failed transcript, one still running at the timeout, and a request failure (SDK or network) are `TranscriptionError` |
| `test_access_rule.py` | 14 | `may_use_app` (active and a known role), `assert_may_sign_in` (403, WARNING), `get_current_user` refuses a removed role or disabled account with 401 and a WARNING |
| `test_auth_endpoints.py` | 15 | Register, login, refresh, logout, `/me` (role in the response) |
| `test_auth_schemas.py` | 11 | Auth request/response schemas; `role` required but nullable |
| `test_config.py` | 4 | `app_debug` off unless `APP_DEBUG` is set, on when set; transcription defaults to the EU endpoint and Universal-3.5 Pro with a Universal-2 fallback; models read from a JSON env value |
| `test_auth_service.py` | 18 | Password hashing, tokens, register (no role on creation, bootstrap elevation); password login refused without a role or when disabled |
| `test_bootstrap_admins.py` | 6 | Startup bootstrap sweep |
| `test_cost_tracker.py` | 9 | LLM, embedding and transcription cost calculation; AssemblyAI rate plus diarization from settings |
| `test_db_bootstrap.py` | 11 | Bootstrap config from the environment (defaults, overrides, every missing name listed); URL encoding of credentials; random passwords; secret merge keeps other keys; placeholder detection; exit code 2 without settings |
| `test_db_session.py` | 1 | Engine command timeout |
| `test_db_session_scope.py` | 28 | Every route's session is function-scoped, so it commits before the response (one case per route); a failed commit answers 500, not success |
| `test_entitlement_coverage.py` | 37 | Every `/api/v1` route carries a guard or is listed public or self-scoped; placement-id routes carry a placement-scope guard |
| `test_entitlements.py` | 35 | Global vs scoped roles, fail-closed for no role or unknown roles, 404-on-denial, role gate, bootstrap elevation rules |
| `test_health.py` | 1 | Health endpoint |
| `test_llm_factory.py` | 11 | Cached Azure OpenAI clients with timeout |
| `test_media_files.py` | 30 | Each allowed extension's signature matches and another type's does not; extension check names the allowed list; clean file names (spaces, path parts, `..`, 200 chars, empty); the stream passes a matching file unchanged, checks a signature split over 1-byte chunks or shorter than the window, releases no byte of a wrong file, stops at the cap as bytes arrive, refuses an empty file |
| `test_memory.py` | 11 | RSS probe and tracemalloc diagnostics |
| `test_multipart_upload.py` | 7 | Copied: small chunks buffered into 8 MiB parts, a short stream as one part, a custom part size, an empty stream, a failed part and cancellation abort the upload, a part size under S3's 5 MiB floor refused |
| `test_processing_ownership.py` | 8 | Takeover order (sweeps, start, re-queues), retry, non-fatal steps, heartbeat loss |
| `test_processing_queue.py` | 27 | Priorities (chat < session < backlog), dedup, dispatch order, workers, stragglers, runner registry |
| `test_processing_status_api.py` | 11 | Queue status route; manager/admin only |
| `test_rate_limiting.py` | 4 | Auth rate limits |
| `test_refresh_tokens.py` | 15 | Refresh token storage, rotation, revocation; refresh refused, every token revoked and a WARNING logged for no role, a disabled account or a missing user |
| `test_register_import_file.py` | 13 | Register CSV file checks: line numbers, Excel BOM, header case and spaces, trimmed cells, blank lines skipped; missing and unknown columns named; not UTF-8, over 1 MB, empty or header-only, over 1,000 rows refused; name normalisation |
| `test_security_middleware.py` | 10 | Security headers, CORS lockdown |
| `test_sso_endpoints.py` | 9 | SSO config and callback routes; a refused sign-in answers 403 with the reason and sets no cookie |
| `test_sso_service.py` | 37 | Token exchange (identity scopes only, no `offline_access`), id_token validation, tenant allowlist; guests refused by `acct` (missing claim refused); user found by oid, then email (linked, name taken); no row for an unknown account; bootstrap admin created as `pmo_manager`; full flow refuses no role, disabled or unknown; sign-in stores no Microsoft token |
| `test_storage_local.py` | 9 | Copied: local storage upload, stream, download, delete, exists, path |
| `test_storage_s3.py` | 12 | Copied, against a mocked client: put, multipart stream without joining, an empty stream stored as an empty object, a failed part aborts, get, delete, exists (found, 404, other errors re-raised), presigned URL, endpoint override |
| `test_upload_service.py` | 7 | Session media key; missing name, other type and an over-cap declared size refused; a recording is stored under the session; a renamed file and more bytes than declared past the cap are refused and leave nothing |
| `test_url_download_service.py` | 12 | Pre-check by HEAD, or a one-byte ranged GET when HEAD is refused (total from Content-Range); over-cap size, sign-in required and an unsupported type refused; extension from the content type; an internal address refused before any request; download streamed into the session key; a web page instead of a recording, an over-cap body and a redirect to an internal address refused and nothing kept; an error status is a download error |
| `test_url_guard.py` | 30 | Internal addresses (private, loopback, link-local and metadata, CGNAT, unspecified, multicast, IPv6 loopback, link-local and ULA, IPv4-mapped) refused, public ones allowed; only https; a host with any internal address refused; internal IP literals refused without a lookup; unresolvable host refused; the request goes to the checked IPv4 or IPv6 address with Host and SNI set to the name; a redirect to an internal host or to http refused; a public redirect pinned again; too many redirects refused |
| `test_user_role_cli.py` | 9 | Role CLI arguments: grant, `none`, `--list`; bad arguments exit 2; a bad address exits 2 without a commit |

## Backend integration tests (`backend/tests/integration/`)
| File | Tests | Covers |
|------|-------|--------|
| `test_auth_api.py` | 11 | Auth flow against Postgres; password login without a role answers 403 with no cookie |
| `test_bootstrap_admins.py` | 3 | Elevation of listed users; a global role is left alone |
| `test_db_bootstrap.py` | 5 | First run creates a non-superuser login that owns the database and `public` schema, can run DDL and use `vector`; a second run keeps the password; rotation invalidates the old password; `run` writes a `DATABASE_URL` that connects and leaves it alone on re-run; an existing login with no URL exits 1 until `--rotate-password` |
| `test_db_command_timeout.py` | 1 | asyncpg command timeout |
| `test_health.py` | 1 | Health endpoint |
| `test_migrations.py` | 4 | `alembic upgrade head` on an empty DB, `alembic check` (no drift), downgrade and re-upgrade; 002 drops the Microsoft token columns and its downgrade restores them; 003 adds the session and recordings tables and the `processing_costs.session_id` key, and its downgrade removes them |
| `test_register_api.py` | 20 | Register routes: a manager builds a placement; names tidied; uniqueness (client name, consultant email, project per client, placement key) answers 409; end before start, inactive or role-less people and unknown references answer 422; required fields cannot be cleared; partial PATCH with null clearing; ending a placement; a PS reads only their own placement by id (404 otherwise) and cannot list or edit (403); the user list has no secrets |
| `test_register_import.py` | 10 | CSV import: a dry run previews and writes nothing; Confirm writes and a re-import is unchanged (rows reuse what earlier rows created); any row error writes nothing; filled cells overwrite, empty cells keep; a consultant entered by name gains the email; two consultants with one name need an email; people must be users with a role, a different role warns; not a `.csv` is 422; scoped roles cannot import |
| `test_placement_scope.py` | 10 | Who can read a placement (each role); denial identical to a missing row; `access_log` rows only for permitted logged reads |
| `test_processing_ownership.py` | 6 | Advisory lock acquire, hold, heartbeat, release |
| `test_session_schema.py` | 10 | A new session is `uploaded` with no kind, no rejected quotes and no node errors; a new folder is unmatched with no candidates; one session per recording and one transcript per session; kind, source, status and match status outside their sets refused; a session's cost rows outlive it (key set to null); a cost for an unknown session refused |
| `test_sign_in_access.py` | 8 | A role granted by email is linked at the first SSO sign-in; an unknown account leaves no row; change, list, remove-nothing and bad-address cases; removing a role revokes every refresh token; refresh refused once the role is gone; refresh works while it is held |
| `test_users_api.py` | 11 | Granting creates a user by email or changes an existing role; not an email is 422; removing a role ends the sessions; unknown id 404; the last active PMO manager keeps the role (a disabled one does not count), handing over first works, and the service the CLI uses refuses too; scoped roles cannot change roles (403) |

## Frontend unit tests (`frontend/src/`)
| File | Tests | Covers |
|------|-------|--------|
| `app/auth/callback/microsoft/page.test.tsx` | 8 | Error param, missing code, missing PKCE verifier, code exchange payload and redirect to `/`, exchange failure, a refused sign-in shows the backend's reason, a non-refusal keeps the generic message, back to login |
| `app/layout.test.tsx` | 3 | Metadata name and tagline; toast region mounted; toasts shown |
| `components/admin/AdminView.test.tsx` | 10 | Opens on the register for `pmo_manager` and `admin`; the tabs in order (Register, Import, Users and roles, Processing); the tab in the URL opens (the queue polls only on its tab); choosing a tab writes `?tab=`; an unknown tab falls back; no tabs and the no-access message for `sme`, `tech_lead`, `ps` and no role |
| `components/admin/register/ImportTab.test.tsx` | 3 | Preview then Confirm of a clean file; Confirm stays disabled while a row has an error; a refused file shows the reason |
| `components/admin/register/PlacementDialog.test.tsx` | 3 | End date before the start refused in the form; every field sent with empties as null; a failed save stays open with the API's message |
| `components/admin/users/UsersTab.test.tsx` | 4 | Users listed with role, you marked, Microsoft sign-in state; the last PMO manager refusal shown and nothing refreshed; email and role required to give access; a change reports its message and refreshes |
| `components/common/DataTable.test.tsx` | 3 | Search over every column; sort by header; empty and loading messages |
| `components/admin/ProcessingStatusPanel.test.tsx` | 6 | Memory formatting; hidden when disabled; idle and busy queues; running jobs by kind, no links; memory diagnostics; request error |
| `components/auth/LoginForm.test.tsx` | 7 | Microsoft button only; progress and error states; no password or sign-up |
| `components/common/DateRangeFilter.test.tsx` | 8 | From/To inputs, clear button, change callbacks |
| `components/common/EmptyState.test.tsx` | 6 | Title, description, link and button actions |
| `components/common/ErrorFallback.test.tsx` | 5 | Default and custom title and description, reset |
| `components/layout/Sidebar.test.tsx` | 3 | Nav for global roles (with Admin) and others (without); risk board at `/` |
| `components/layout/ThemeToggle.test.tsx` | 4 | Light, dark and system options |
| `components/providers/AuthProvider.test.tsx` | 6 | Session restore with role; no-role user stays; signed-in user leaves `/login` for `/`; signed-out visitor stays on `/login`; expiry sends to `/login` |
| `hooks/useRegister.test.ts` | 3 | Create with POST, update with PATCH on the record's path; import sends the file and the dry-run flag |
| `hooks/useProcessingStatus.test.ts` | 3 | No request when disabled; 5 s / 30 s polling; busy flag |
| `hooks/useSSOLogin.test.ts` | 3 | Authority from the server and identity scopes only; single-tenant authority; config failure |
| `hooks/useScrollRestore.test.ts` | 3 | Save and restore scroll position per key |
| `lib/api.test.ts` | 8 | `patch` sends PATCH with the body and token, and raises the API's message; one refresh and retry on 401, no refresh loop, session expiry, refresh timeout, shared refresh, no refresh for auth endpoints |
| `lib/pkce.test.ts` | 7 | Verifier and S256 challenge; verifier stored once and cleared |
| `lib/register.test.ts` | 3 | Enumeration labels; empty and none become null; skills split on commas |
| `lib/roles.test.ts` | 4 | The five roles; `pmo_manager` and `admin` global; scoped roles and no role not global |

## Frontend e2e tests (`frontend/tests/e2e/`)
| File | Tests | Covers |
|------|-------|--------|
| `auth.setup.ts` | 1 | Registers and signs in with local auth (the user is a bootstrap admin in `docker-compose.yml`, since sign-in needs a role), copies the refresh cookie, lands on the risk board, saves the storage state |
| `admin-users.spec.ts` | 1 | A PMO manager gives a new address the PMO SME role (listed, not signed in yet), then removes it |
| `admin-register.spec.ts` | 2 | A PMO manager adds a client in the dialog, and the same name again is refused with the reason; a CSV is previewed, confirmed, and its placement found on the register |
| `auth.spec.ts` | 8 | Login page offers only Microsoft (no password, no sign-up); `/signup` redirects or 404s; signed-in user lands on the risk board, is sent from `/login` to `/`, opens Actions, sees the app name |
