# Sprint 0: Bootstrap

**Status**: `planning-in-progress`
**Duration**: 2026-10-06 – TBD
**Objective**: Bootstrap the repository: stack copied from Interview Intelligence, SSO sign-in with roles, empty dashboard deployed to staging, Graph app registration created and Teams permission request submitted

---

## Research Findings Summary
<!-- Populated during sprint planning -->
- **Teams Graph access (2026-10-06)**, full detail and sources in `docs/integrations/TEAMS-GRAPH-SETUP.md`:
  - Teams APIs are no longer metered as of 2025-08-25, so no Azure billing setup is needed
  - The least-privileged app permission for `GET /chats/{id}/messages` is RSC `ChatMessage.Read.Chat`; chat RSC defaults to `ManagedByMicrosoft` (members can consent)
  - Whether `Chat.Read.All` still needs Microsoft's protected-API approval is unconfirmed (the request page has been removed)
  - Polling: `$top` max 50; `$filter` on `lastModifiedDateTime gt` requires `$orderby` on the same property, descending only
- **GitHub**: branch protection and rulesets on private repos need GitHub Pro (HTTP 403 on the free plan)

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|

## Task Checklist
<!-- Populated after plan approval -->

>>> CURRENT PHASE: Planning

## Session State (last updated: 2026-10-06 15:57)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Planning (pre-planning setup)
- **Phase progress**: 3 of 11 bootstrap checklist items done (scaffolding applied; PRD, ARCHITECTURE and BACKLOG written; GitHub repo created) and the Entra Graph app is registered. Sprint task checklist not yet planned
- **Last completed task**: Teams Graph access Part A1–A3 (certificate, Entra app `d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3`, connector app package); package submitted to the org and pending; admin request sent
- **Next task**: Run `/sprint-start` to plan Sprint 0. After admin approval, add the connector app to a test group chat and run A5 in `docs/integrations/TEAMS-GRAPH-SETUP.md`
- **Last commit**: [will be filled after commit]
- **Uncommitted changes**: none (just committed)
- **Blockers**: Teams connector app pending tenant admin approval (external; does not block sprint planning)
- **Tests passing**: 0 unit + 0 integration + 0 frontend = 0 (no code yet)
- **Files created this session**: `docs/integrations/TEAMS-GRAPH-SETUP.md`, `scripts/teams/New-GraphCertificate.ps1`, `scripts/teams/Register-GraphApp.ps1`, `scripts/teams/verify_chat_access.py`, `teams-app/manifest.template.json`, `teams-app/build_package.py`, `teams-app/color.png`, `teams-app/outline.png`
- **Files modified this session**: `.gitignore`, `docs/planning/BACKLOG.md`, `docs/planning/CURRENT-SPRINT.md`
- **Key decisions this session**: see Decisions Log (Teams groups, permission route, repo, pnpm)
- **Recovery instructions**: Interview Intelligence repo is at `E:\E Projects\Interview Intelligence Platform` (uv backend, pnpm frontend, Makefile targets match). Never copy its `infra/terraform.tfstate*` or `terraform.tfvars`. Sprint 0 planning still needs BACKLOG decisions 8, 9 and 10 (hostnames).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Python deps via uv, frontend via pnpm | Matches the Interview Intelligence repo (`backend/uv.lock`, `frontend/pnpm-lock.yaml`); npm was the first answer, corrected 2026-10-06 after checking the repo |
| Dev/test/lint/format via Makefile targets (`make dev`, `make test`, `make lint`, `make format`) | The Makefile is copied from Interview Intelligence; target names to be confirmed once it lands |
| `docs/PRD.md` is a complete, verbatim conversion of the kickoff Project Starter document | The kickoff document is the core spec; nothing in it may be lost or paraphrased |
| Sprint 0 = Phase 0 (Bootstrap) | Matches the PRD's phased delivery plan |
| Local-only developer config is excluded via `.git/info/exclude`, not `.gitignore` | Keeps the committed ignore file to project concerns only |
| Teams groups: one group chat per consultant (BACKLOG #1) | User decision; matches the PRD's suggested answer |
| Teams permission route: RSC with `Chat.Read.All` fallback in parallel (BACKLOG #4) | User decision; RSC is least-privileged and visible to chat members |
| GitHub repo `Abhishekkv99/pmo-intelligence`, private; `main` and `develop` pushed | User decision; same owner as Interview Intelligence |
