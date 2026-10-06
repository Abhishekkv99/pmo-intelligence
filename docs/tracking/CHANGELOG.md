# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
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
