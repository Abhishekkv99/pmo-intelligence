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
- Project documentation: PRD, architecture, API, roadmap, backlog, sprint templates.
