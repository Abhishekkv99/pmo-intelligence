# Sprint Audit Report

> **This file is a MANDATORY artifact.** It must be filled out BEFORE the handover document is created.

## Sprint: 03 (Visual Redesign)
## Date: 2026-10-13

The Sprint 2 report is in git history ("docs: complete sprint 2 audit and handover") and summarised in `docs/handover/sprint-02-handover.md`.

**Status**: PASSED. The exit gate was met on staging on 2026-10-13: the user walked the sign-in page, the shell, the risk board and a placement page in light and dark (sign-in and the shell at phone width) with five placements entered by the quick add, and approved them; the one change asked for (the risk board's project in its own column) is in BACKLOG. The sprint was frontend only: no backend, infrastructure, CI or setting changed.

---

## Verification Checklist

Check each item. Mark `[x]` only after actually verifying (not from memory).

### Test Counts
- [x] Backend tests verified by running test command → count matches TESTS.md (`uv run pytest -q -rf`: 1045 passed in 221 s, no failure; `pytest --collect-only`: 763 unit and 282 integration; the backend is unchanged since the CDM run of 2026-10-11, so its rows stand as compared then)
- [x] Frontend tests verified by running test command → count matches TESTS.md (`vitest run --maxWorkers=4`: 40 files, 265 passed; `vitest list --json` per file matches all 40 rows; `playwright test --workers=1` against the rebuilt compose stack: 23 passed, and each spec's count matches its row)
- [x] Grand total matches (763 + 282 + 265 + 23 = 1333, as in TESTS.md)

### Lint
- [x] Linter passes with no errors (ruff check, ruff format check on 216 files, mypy strict on 123 source files; eslint, `tsc --noEmit`, Prettier check: all exit 0)

### Documentation Verification
- [x] CHANGELOG.md has entry for this sprint (`[Unreleased]`, Changed and Fixed: the Twilight look and fonts, the logo, the shell, the sign-in page, the risk board, the placement page, the sessions pages, Admin, Actions and Settings, reduced motion, the sidebar's active item on a placement page)
- [x] FEATURES.md has all new features logged (the "Sprint 3: Visual Redesign" section has a row for each of the 7 code commits' deliverables; one older row's path was stale, finding S3-1)
- [x] TESTS.md row counts match actual test output (all rows, above)
- [x] BACKLOG.md completed items checked off (the redesign item done; new this sprint: the top-bar search, the risk board's project column from the walk-through, the unused chart-entrance CSS from this audit; the `sessions.spec.ts` race kept, it passed in this run)
- [x] ROADMAP.md completed milestones checked off (the four Sprint 3 items ticked in the phase commits that delivered them; the exit gate marked met)
- [x] ARCHITECTURE.md reflects current state ("Frontend (as built)" compared with the code by a separate read: versions, paths, quoted copy, breakpoints, polling intervals; one duplicated phrase and two wordings fixed, finding S3-6; status line moved to "Sprint 3 complete")
- [x] API.md accurately describes endpoints (no backend change this sprint: `git diff 9a2963f..HEAD -- backend` is empty, so the Sprint 2 audit's 40-route comparison and the later CDM and quick-add updates stand)
- [x] .env.example lists all env vars (unchanged with `app/config.py`, both untouched since 9a2963f)
- [x] No tooling or authorship traces in any committed file (`git grep` of tracked files for the forbidden names, attribution trailers and the rules folder's path: none; no tool configuration file tracked; the 8 Sprint 3 commit messages are clean)
- [x] Git commits follow conventional commit format (8 commits since 9a2963f: 7 `feat`, 1 `docs`, all listed types)
- [x] Dependency lists current (one package added, `motion` 13.4.6, pinned exactly, named in ARCHITECTURE and DESIGN; the shadcn sidebar, breadcrumb and avatar are source files, not packages; `pyproject.toml` and `uv.lock` unchanged)

**File paths**: 801 backtick path references in README.md, ARCHITECTURE.md, DESIGN.md, API.md, DEPLOYMENT.md, TESTS.md, FEATURES.md, CHANGELOG.md, BACKLOG.md, ROADMAP.md and CURRENT-SPRINT.md were checked against the tracked files and folders (bare names against any tracked file of that name). All resolve except non-paths (API routes, module specifiers such as `motion/react` and `next/font/google`, a CIDR, a date format, an image tag, a secret name, the repository name, an S3 prefix, a media type), the git-ignored `backend/.env`, `.next/types` and `frontend/AGENTS.md`, files this sprint removed named as removed (`Sidebar.tsx`, `Header.tsx`, `favicon.ico`, the CSV import's files), `docs/handover/sprint-03-handover.md` (written after this audit), the planned `config/v2.json`, and one stale path (S3-1).

**Design doc**: every statement in `docs/DESIGN.md` was read against the code (tokens converted from oklch, contrast ratios recomputed, sizes and behaviour from the components' classes). Colours, ratios, fonts, logo, shell sizes, icons, quoted copy and polling matched; eleven statements did not (S3-4) and the status line was stale (S3-5). What needs a browser (sticky columns, the drawer, reduced motion) was checked in the e2e run and the user's walk-through.

**Commands**: run in this audit: the suites and linters above (`make test` and `make lint` run the same commands), `docker compose up --build -d --wait frontend`, the e2e run. No make target was added this sprint.

---

## Findings

All six were found by this audit and fixed in it. Every finding has a local rule and a Learnings Log line.

| # | What was wrong | Root cause | Rule added/updated |
|---|---------------|-----------|-------------------|
| S3-1 | FEATURES.md's Sprint 1 "Sessions page" row named `frontend/src/app/sessions/page.tsx`, which Phase 2 moved to `frontend/src/app/(app)/sessions/page.tsx` | Phase 2 moved seven page folders but updated only the rows of the pages it was redesigning; later phases fixed their own rows, and nothing searched the docs for the old paths | Sprint workflow: in the commit that moves a file, `git grep` the old path in docs and README and update every hit |
| S3-2 | README's Documentation table did not list `docs/DESIGN.md` (new in Phase 1) or `docs/DEPLOYMENT.md` (Sprint 0) | The README rule covers new make targets only; nothing asks for a new doc's row | Sprint workflow: a new file under `docs/` gets a README Documentation row in the same commit |
| S3-3 | DEPLOYMENT.md's status line, which records every deploy (frontend-only ones included), had none of Sprint 3's five frontend deploys | The phases changed no infrastructure, so DEPLOYMENT.md was left out of every doc list; the deploy facts arrive after the push and were written only into the sprint file's Session State | Sprint workflow: every deploy gets a DEPLOYMENT status entry in the next commit, and every phase that pushes names DEPLOYMENT.md in its doc list |
| S3-4 | Eleven DESIGN.md statements differed from the code: display type "up to 76px, 0.96" (62px, 0.98), small-caps tracking 0.2em everywhere (0.05em outside the eyebrow), "white" on primary at 16.9:1 (warm white, 16.2:1), a footer hairline on every auth page (login only), 24px highlight titles (20px below 640px), 16px gutters below 1024px (40px from 640px), client · project clamped to two lines (only the action is), a quote's link "to the moment" (to the call), the status word coloured in flight (only the dot), "pills" for `rounded-md` sub-tabs, a CSS chart entrance that no component uses | Sections were written from the approved mockup and the plan's wording, and the built values (tuned in the browser during each phase) were not read back into the doc | Sprint workflow: DESIGN.md values are copied from the built classes and tokens, and each touched line is read beside its component before the phase commit. The unused CSS is in BACKLOG (Tech Debt) |
| S3-5 | DESIGN.md's status line began "Sprint 3 Phase 4 (2026-10-12)" while listing Phases 5 to 7 | Each phase appended its part to the body of the line without rewriting its head | Sprint workflow: a status line's leading phase and date change whenever a phase is added to it |
| S3-6 | ARCHITECTURE's Placement page row read "on the left the health chart the health chart (Recharts 2 …" | A replacement inserted before an existing phrase was not read back in full | Sprint workflow: read every changed doc line whole in `git diff --word-diff` before committing |

---

## Audit Result
- [x] All checklist items verified
- [x] All findings fixed (S3-1 to S3-6 in this audit)
- [x] Every finding has a rule (6 rules for 6 findings, all in the sprint workflow rules)
- [x] Learnings Log updated (6 lines)
- [x] **AUDIT COMPLETE** — **AUDIT PASSED** → handover document can be created
