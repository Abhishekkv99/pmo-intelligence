# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Security
- Sign-in no longer stores users' Microsoft access and refresh tokens, and asks Microsoft for identity scopes only (`openid email profile`, no `offline_access`). Migration 002 drops `users.ms_access_token`, `ms_refresh_token` and `ms_token_expires_at`; the unused `refresh_microsoft_token` is removed.

### Fixed
- `APP_DEBUG` now defaults to off, so a backend container that does not set it (the migration container, a one-off ECS task) no longer echoes every SQL statement into its logs. Compose and `.env.example` turn it on for development.

### Added
- Manual staging redeploy: run the CI workflow on `develop` with `target` set to backend, frontend or both; it runs that side's checks and e2e, then deploys.
- Backend skeleton: FastAPI app with security headers, CORS, rate limiting and a health endpoint.
- Sign-in with Microsoft Entra ID (authorization code + PKCE) and local password auth for development and CI; refresh-token rotation.
- Role entitlement: `pmo_manager`, `sme`, `tech_lead`, `ps`, `admin`.
  - Placement-scope guards answer 404 on denial and log every denial.
  - A route-coverage test fails the build for any unguarded route.
- Access log writer for reads of consultant data.
- Bootstrap PMO managers from `BOOTSTRAP_ADMIN_EMAILS` (elevate-only).
- Processing queue (chat, session and backlog priority tiers; runners registered per job kind) and processing ownership lock with heartbeat and registered takeover steps.
- Processing status endpoint for PMO managers and admins.
- Migration 001: users, refresh tokens, consultants, clients, projects, placements, processing jobs and costs, access log; pgvector enabled.
- Teams Graph access: certificate and app registration scripts, a chat-access verification script, and the Teams connector app package.
- Frontend skeleton (Next.js 16.3.8, React 19.2, shadcn/ui, SWR, dark mode): sign-in with Microsoft (PKCE), session restore through the refresh cookie, and a route guard.
- Sidebar with Risk board, Actions, Admin and Settings. Admin is shown to PMO managers and admins only; anyone else opening `/admin` sees a no-access message.
- Admin page with the processing queue: queue depth, running jobs by kind and backend memory.
- Risk board, Actions and Settings placeholder pages.
- Frontend tooling: Prettier, `typecheck`, `format` and `format:check` scripts; pnpm 12 pinned with `packageManager`; Node 22 or later.
- Frontend unit tests (Vitest) and Playwright end-to-end tests for sign-in.
- Project documentation: PRD, architecture, API, roadmap, backlog, sprint templates.
- Local stack with Docker Compose: PostgreSQL 16 with pgvector, backend and frontend, each with a health check.
- Backend Dockerfile (non-root, uv 0.9.18) and frontend Dockerfile (non-root, pnpm 12.6.0, Next.js standalone server bound to all interfaces); one `.dockerignore` per image.
- Makefile targets for the stack, migrations, tests (`test`, `test-e2e`), lint (ruff, mypy strict, eslint, typecheck, Prettier check) and formatting.
- Configurable host ports for the local stack (`PMO_API_PORT`, `PMO_WEB_PORT`; defaults 8000 and 3000) so it can run beside other projects.
- `.env.example` listing every backend setting with local defaults.
- CI on GitHub Actions: path-filtered backend and frontend checks, end-to-end tests against the compose stack, and a staging deploy from `develop` that runs only after the checks pass (skipped until the deploy variables are set).
- README with prerequisites, quick start and common commands.
- Terraform state bucket in the PMO sandbox account (`infra/bootstrap/`): versioned, encrypted, public access blocked, TLS-only; state locking with native S3 lock files.
- Deployment guide (`docs/DEPLOYMENT.md`): account access through SSO, tooling, bootstrap order, the app secret's keys, the database bootstrap, Azure OpenAI, credential expiry reminders, and rollback of an app deploy (image retag, migrations) and of Terraform state.
- Terraform for the shared stack (VPC, ECR, ECS cluster, GitHub OIDC deploy role, deny-deletion policy) and a reusable environment module, applied for staging at `pmo-intelligence-staging.itcapp.ai`: HTTPS load balancer, PostgreSQL 16, app secret, media bucket, SES identity and ECS services.
- Database bootstrap (`app/cli/db_bootstrap.py`, `make db-bootstrap ENV=staging`): a one-off ECS task that creates the `pmo_app` login, gives it the database, enables pgvector and writes `DATABASE_URL` into the app secret; idempotent, with optional password rotation.
- Terraform for PMO's own Azure OpenAI (`infra/azure/`): resource group and resource in Sweden Central with Data Zone Standard deployments of `gpt-5.4-mini` and `text-embedding-3-small` for staging.
- Credential expiry reminders: scheduled emails 30, 14 and 3 days before each recorded credential expiry (the Teams Graph certificate first).
- Sign-in limited to members of the InformationTech tenant who hold a role: guests are refused by the id-token `acct` claim, no account is created for anyone else at sign-in (bootstrap admins excepted), and a removed role ends sessions on refresh and within 15 minutes on open pages. The callback page shows why a sign-in was refused.
- `make user-role ENV=<env> EMAIL=... ROLE=...` (`ROLE=none` to remove, `ARGS=--list` to list): grants roles by email as a one-off ECS task until the Admin users page exists.
- Entra SSO app registration script (`scripts/entra/Register-SsoApp.ps1`): single-tenant app with Web redirect URIs, user consent (assignment optional), and a client secret per environment written straight into the app secret; staging sign-in configured, with its secret's expiry reminded.
