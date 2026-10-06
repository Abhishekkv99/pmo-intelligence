# Sprint 0: Bootstrap

**Status**: `planning-in-progress`
**Duration**: 2026-10-06 – TBD
**Objective**: Bootstrap the repository: stack copied from Interview Intelligence, SSO sign-in with roles, empty dashboard deployed to staging, Graph app registration created and Teams permission request submitted

---

## Research Findings Summary
<!-- Populated during sprint planning -->

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|

## Task Checklist
<!-- Populated after plan approval -->

>>> CURRENT PHASE: Planning

## Session State (last updated: 2026-10-06 15:04)
- **Sprint**: 0 — Bootstrap
- **Current phase**: Planning (pre-planning setup)
- **Phase progress**: 2 of 11 bootstrap checklist items done (PRD "Repo bootstrap checklist": project scaffolding applied; PRD, ARCHITECTURE and BACKLOG written). Sprint task checklist not yet planned
- **Last completed task**: Project docs written: full PRD from the kickoff document, architecture, roadmap, backlog with the 10 open decisions
- **Next task**: Start the Teams Graph permission request and create the private GitHub repo `pmo-intelligence` (external lead time), then run sprint planning for Sprint 0
- **Last commit**: [will be filled after commit]
- **Uncommitted changes**: none (just committed)
- **Blockers**: None
- **Tests passing**: 0 unit + 0 integration + 0 frontend = 0 (no code yet)
- **Files created this session**: `.gitignore`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/assets/architecture.png`, `docs/assets/delivery-roadmap.png`, `docs/planning/{CURRENT-SPRINT,BACKLOG,ROADMAP}.md`, `docs/tracking/{CHANGELOG,FEATURES,TESTS,SPRINT-AUDIT}.md`, `docs/handover/TEMPLATE.md`
- **Files modified this session**: none (initial commit)
- **Key decisions this session**: see Decisions Log
- **Recovery instructions**: Repo initialised on `main` with one commit; create `develop` from it. Sprint 0 planning needs the local path to the Interview Intelligence repo and answers to BACKLOG decisions 4, 8, 9 and 10.

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Python deps via uv, frontend via npm | Matches the Interview Intelligence stack being copied |
| Dev/test/lint/format via Makefile targets (`make dev`, `make test`, `make lint`, `make format`) | The Makefile is copied from Interview Intelligence; target names to be confirmed once it lands |
| `docs/PRD.md` is a complete, verbatim conversion of the kickoff Project Starter document | The kickoff document is the core spec; nothing in it may be lost or paraphrased |
| Sprint 0 = Phase 0 (Bootstrap) | Matches the PRD's phased delivery plan |
| Local-only developer config is excluded via `.git/info/exclude`, not `.gitignore` | Keeps the committed ignore file to project concerns only |
