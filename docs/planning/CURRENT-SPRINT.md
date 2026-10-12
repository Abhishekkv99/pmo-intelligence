# Sprint 3: Visual Redesign

**Status**: `in-progress` (plan approved 2026-10-12)
**Duration**: 2026-10-12 – 2026-10-23 (2 weeks)
**Objective**: a modern, management-ready look, designed page by page in Google Stitch and approved by the user before each page is built. The demo path comes first: the design system, a new app shell, a showcase sign-in page, the risk board and the placement page. Then the sessions pages and Admin if time allows; anything left goes to BACKLOG. Teams chat (PRD Phase 3, ROADMAP Milestone 3) moves to Sprint 4.
**Exit gate**: the user approves the sign-in page, the risk board and the placement page on staging after a demo walk-through (light, dark, and phone width for sign-in and the shell); CI green.
**Branch**: `develop`
**Previous sprint**: Sprint 2 (Health v1), complete 2026-10-11 without its exit gate; see `docs/handover/sprint-02-handover.md`. Its plan, session notes and Decisions Log are in git history (`9a2963f`); the post-sprint quick add (`73045d8`) and CDM (`8368ce9`) work is recorded there too.

---

## Research Findings Summary
- **Stitch**: no project for PMO yet. Its tools create a project and a design system, generate a screen from a text prompt, generate 1–5 variants (refine, explore or reimagine), edit screens, and read a screen (its HTML and a screenshot link). Screens are generated from text only, so every prompt carries made-up sample data and nothing from staging is ever sent. The HTML is a reference: pages are rebuilt in the app's own components (shadcn/ui, Tailwind tokens), keeping dark mode, the RAG tokens, polling, access rules and tests.
- **Current frontend** (surveyed 2026-10-12):
  - Neutral shadcn tokens (oklch) in `src/app/globals.css`, with the `--risk-*` RAG tokens and `--chart-1`…`5`; Geist fonts; next-themes with class switching.
  - The sidebar (`components/layout/Sidebar.tsx`) has text items and no icons, and is neither collapsible nor usable on a phone. The header repeats the app name as the page's `h1`.
  - No logo: the only asset is `src/app/favicon.ico`, and there is no `public/`.
  - The sign-in page is a centred card (`app/login/page.tsx`, `components/auth/LoginForm.tsx`).
  - shadcn `new-york`, `radix-ui` 1.4, lucide; no sidebar, tooltip, sheet or avatar component yet; no animation library.
- **Tokens and contrast**: Tailwind 4 keeps oklch values in `:root`/`.dark` and maps them through `@theme inline`, as the app already does.
  - White on indigo #6366F1 is about 4.47:1, just under WCAG AA, so the light `--primary` is near #4F46E5 (`oklch(0.511 0.262 277)`) and the dark one near #818CF8 with a dark foreground; #6366F1 stays for the logo.
  - `--accent` and `--secondary` stay tinted neutrals, since menus use `--accent` for hover.
  - Muted text on dark surfaces is where dark themes usually fail contrast, so it is checked.
- **Forced dark sign-in**: a wrapper with the `dark` class (and `color-scheme: dark`) redefines the variables beneath it, and the `dark:` variant (`@custom-variant dark (&:is(.dark *))`) follows it. The user's theme choice is never changed (no `setTheme`). Portals (toasts, dialogs, tooltips, selects) render on `body`, outside the wrapper, so the sign-in page uses none and shows errors inline.
- **shadcn sidebar**: added with the pinned CLI (`pnpm exec shadcn add sidebar`).
  - It brings sheet, tooltip and `hooks/use-mobile.ts`, and offers to overwrite button, input, separator and skeleton; the existing files are kept and `globals.css` is checked afterwards.
  - The open state lives in the `sidebar_state` cookie, read with `!== "false"` so the sidebar starts open; `cookies()` is async in Next 16.
  - jsdom needs a `matchMedia` stub.
- **motion**: 14.0.0 is a new major (2026-10-02) and 14.1.0 is from 2026-10-09, so 13.4.6 (2026-09-29) is pinned exactly. It works in client components only (`motion/react`), with `MotionConfig reducedMotion="user"`. jsdom has no `IntersectionObserver`, so no `whileInView` without a stub. The existing `.chart-animate` keyframes also get a reduced-motion block.
- **Favicon**: `src/app/icon.svg` (a Next metadata file) replaces `favicon.ico`. `src/proxy.ts`'s matcher lets only `favicon.ico` through, so it must also pass `icon.svg`, or signed-out browsers are sent to `/login` for the icon.
- **Sign-in UX**: enterprise SSO as the single primary action, with clear inline errors; a second column only for context, which here is the showcase.
- **Tests that read visible text**:
  - The e2e auth setup waits for the heading "Risk board", and Playwright matches names as case-insensitive substrings in strict mode, so no new heading may contain "Risk board".
  - `auth.spec.ts` expects one heading "PMO Intelligence" (the top bar), links "Actions" and "Settings" (no new link may contain those words), and one `[data-slot='card-title']` with "Sign In", so the showcase does not use `CardTitle`.
  - `Sidebar.test.tsx` checks the nav labels and the Risk board href.
  - `PlacementHealthView.test.tsx` checks the link "← Risk board".
- **Code to reuse**:
  - From `components/layout/Sidebar.tsx`, moved: `visibleNavItems`, `getActiveHref`, `globalOnly`.
  - From `lib/roles.ts` and `lib/constants.ts`: `hasGlobalRole`, `ROUTES`, `APP_NAME`, `APP_TAGLINE`.
  - From `components/health/HealthIndicators.tsx`: `HealthBadge`, `TrendIndicator`, `LEVEL_CLASSES`, `NotScored`.
  - From `lib/health.ts`: the formatters and chart helpers.
  - `HealthChart`, for the sign-in mini chart.
  - `ThemeToggle`, as it is.
  - `DataTable`, `EmptyState` and `ErrorFallback`: restyled, not replaced.

## User Decisions Made
| Question | User Choice | Alternatives Offered |
|----------|------------|---------------------|
| Scope | The demo path first (design system and shell, sign-in, risk board, placement page), then the sessions pages and Admin if time allows; leftovers to BACKLOG | Every page; sign-in and shell only |
| Teams chat (Milestone 3) | Sprint 4; the chat RSC check with the Teams admin runs alongside this sprint | Later, after the exit gates; decide at Sprint 4 planning |
| Dates | 2026-10-12 – 2026-10-23 | One week |
| Design review | For each page, 2–3 Stitch variants on made-up data; the user approves one (or asks for edits) before any code | The design system and sign-in only, the rest reviewed in the browser |
| Shell | The shadcn `sidebar` block: an icon per item, collapsible to an icon rail, a drawer on a phone, the user menu in its footer | Restyle the current sidebar |
| Responsive | Sign-in and the shell down to phone width; the data pages desktop-first | Every redesigned page; desktop only |
| Motion | The `motion` library, pinned exactly at 13.4.6, in client components only, reduced motion respected | CSS only (tw-animate-css); 14.1.0 |
| Sign-in preview | A live React component drawn from hard-coded, made-up placements; no API call before sign-in | A static image |
| Accent | Indigo/violet; red, amber and green stay reserved for RAG | Blue; teal; three proposals from Stitch |
| Logo | A simple SVG mark (a pulse line in a rounded square) beside the wordmark, also the favicon | Wordmark only; the user supplies one |
| Sign-in theme | Always dark, whatever the theme setting | Follow the theme |
| Font | Keep Geist and Geist Mono | Inter; Plus Jakarta Sans or Manrope for headings |
| Test text | Page headings, nav labels, aria-labels and test ids stay; the login and header copy follow the design, their tests changed in the same commit | Any text follows the design |
| Design doc | `docs/DESIGN.md` (tokens, logo, shell, page patterns, motion), kept current phase by phase | No separate doc |
| Exit gates | Alongside, not blocking | Not this sprint |
| Route group | The signed-in pages move under `src/app/(app)/` with one shared layout, so the shell stays mounted; URLs unchanged | MainLayout per page |
| Naming the design tool | Committed docs may name Google Stitch (a design tool) | Neutral wording only |

## Task Checklist

>>> CURRENT PHASE: Phase 0 (plan written, awaiting the commit)

Every phase: the Stitch step (variants on made-up data; the user picks one or asks for edits), then code, tests and docs, then the commit checkpoint, then stop. Any screenshot used for design reference comes from the local stack seeded with `seed_e2e_session.py --health`, never from staging. Before e2e: `docker compose up --build -d --wait frontend`, one worker; Vitest with `--maxWorkers=4`.

### Phase 0: Plan
**Code work**
- [x] Plan approved (2026-10-12)

**Doc updates (concurrent)**
- [x] This file; `ROADMAP.md` (a Sprint 3 section; Milestone 3 marked for Sprint 4); `BACKLOG.md` (the redesign item in progress)

**Commit checkpoint**
- [ ] `docs: plan sprint 3`

### Phase 1: Design system, tokens, logo and motion
**Code work**
- [ ] Stitch: create the project "PMO Intelligence" and a design system (indigo seed, neutral, Geist, 8 px roundness, light and dark); one token-sheet screen (buttons, badges, a card, a table row with RAG badges, the logo mark) in 2–3 variants; the user approves one
- [ ] `src/app/globals.css`: the approved values as oklch, light and dark, under the existing token names (`--primary`, `--ring`, `--sidebar-primary`, `--sidebar-ring`, `--chart-1` take the accent); `--brand`/`--brand-foreground` in `@theme inline` if the logo or a gradient needs them; `--risk-*` unchanged; a `prefers-reduced-motion` block for `.chart-animate`
- [ ] `src/components/brand/Logo.tsx` (`LogoMark`, `Wordmark`); `src/app/icon.svg`, `src/app/favicon.ico` deleted; `src/proxy.ts` matcher passes `icon.svg`
- [ ] `pnpm add motion@13.4.6 --save-exact`; `src/components/providers/MotionProvider.tsx` (`MotionConfig reducedMotion="user"`) in `src/app/layout.tsx`
- [ ] Tests: `Logo.test.tsx`; `layout.test.tsx` (the motion provider); the proxy matcher

**Doc updates (concurrent)**
- [ ] `docs/DESIGN.md` (new: tokens, contrast, logo, motion rules), `ARCHITECTURE.md` (root layout, generic UI, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the design tokens, logo and motion setup`

### Phase 2: App shell
**Code work**
- [ ] Stitch: shell variants (expanded, icon rail, phone drawer) around a placeholder board with made-up data; the user approves one
- [ ] `pnpm exec shadcn add sidebar` (existing ui files kept; `globals.css` checked)
- [ ] `src/components/layout/nav.ts`: the nav items with lucide icons, `visibleNavItems` and `getActiveHref` moved from `Sidebar.tsx`; Risk board active on `/placements/*` (fixes the Sprint 2 known issue)
- [ ] `src/components/layout/AppSidebar.tsx`: logo link (not a heading), nav with tooltips, `collapsible="icon"`, rail, user menu with sign-out in the footer
- [ ] `MainLayout.tsx`: `SidebarProvider` from the cookie, `SidebarInset`, the top bar (`SidebarTrigger`, the one `h1` "PMO Intelligence", `ThemeToggle`); `Sidebar.tsx` and `Header.tsx` removed once merged
- [ ] Route group `src/app/(app)/layout.tsx`: `/`, `sessions`, `sessions/[sessionId]`, `placements/[placementId]`, `admin`, `actions`, `settings` moved under it, their own `MainLayout` wrappers removed
- [ ] Tests: `Sidebar.test.tsx` → `nav.test.ts` (same labels and href); `AppSidebar.test.tsx` (active item, Admin hidden for other roles, placement path active); a `matchMedia` stub in `src/test/setup.ts`; all e2e

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Shell and Pages rows with the new paths, `> Status:`), `DESIGN.md` (shell), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the collapsible app shell`

### Phase 3: Sign-in showcase and callback
**Code work**
- [ ] Stitch: 2–3 sign-in variants, desktop and phone, dark, with made-up placements; the user approves one
- [ ] `src/components/auth/AuthShell.tsx` (the forced-dark, full-viewport wrapper with the logo), `Showcase.tsx` (the promise, "calls and chat in, health and early warnings out", 3–4 highlights, a motion entrance), `MiniRiskBoard.tsx` (`HealthIndicators`, and `HealthChart` for the mini chart), `showcase-data.ts` (fixed ISO dates, typed against `types/health.ts`, plainly made up)
- [ ] `LoginForm.tsx` restyled (the button and the Entra note keep their text); `src/app/login/page.tsx`; the callback page inside `AuthShell`; `APP_TAGLINE` only if the approved copy changes it
- [ ] Tests: `Showcase.test.tsx` (the sample rows render; the API client is never called); the mini chart counts its marks; `LoginForm.test.tsx`, the callback `page.test.tsx` and `auth.spec.ts` changed only where the copy changes

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Pages row, auth flow step 1, `> Status:`), `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: add the sign-in showcase`

### Phase 4: Risk board
**Code work**
- [ ] Stitch: 2–3 variants, light and dark, about 12 made-up rows, the filter bar and a red/amber/green/not-scored summary strip; the user approves one
- [ ] `RiskBoard.tsx` (summary strip, filter bar, row styling; the server's order, the filters and the SME view unchanged), `HealthIndicators.tsx` (`health-badge` kept), `DataTable.tsx` styling; the page keeps its h2 "Risk board"
- [ ] Tests: `RiskBoard.test.tsx` updated, with the summary counts (no level counts for an SME); `DataTable.test.tsx`; `risk-board.spec.ts`

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Risk board row, `> Status:`), `DESIGN.md` (tables, badges), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: redesign the risk board`

### Phase 5: Placement page
**Code work**
- [ ] Stitch: 2–3 variants (the header with the overall, six tiles, the chart, flags and evidence, calls, issues, actions); the user approves one
- [ ] `PlacementHealthView.tsx`, `DimensionScores.tsx`, `HealthChart.tsx` (no Fragment among Recharts children), `FlagList.tsx`, `EvidenceItem.tsx`; test ids and the link text "← Risk board" kept; the SME view unchanged
- [ ] Tests: `HealthChart.test.tsx` counts every mark; `PlacementHealthView.test.tsx`; `placement-health.spec.ts`

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md` (Placement page row, `> Status:`), `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: redesign the placement page`

### Phase 6 (if time): Sessions list and session page
**Code work**
- [ ] Stitch variants, the user approves one; `SessionsList.tsx`, `SessionView.tsx`, `AudioPlayer.tsx`, `SessionStatusBadge.tsx` (test ids kept); their tests and `sessions.spec.ts`

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md`, `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: redesign the sessions pages`

### Phase 7 (if time): Admin, Actions and Settings
**Code work**
- [ ] Stitch variants, the user approves one; the Admin tabs and panels restyled (dialogs keep their labels); `EmptyState` with an icon for Actions and Settings; their tests and the admin e2e

**Doc updates (concurrent)**
- [ ] `ARCHITECTURE.md`, `DESIGN.md`, `FEATURES.md`, `TESTS.md`, `CHANGELOG.md`

**Commit checkpoint**
- [ ] `feat: redesign the admin and placeholder pages`

### Phase 8: Staging, demo check, audit and handover
**Code work and setup**
- [ ] The pushes deploy the frontend (both CI filters read before saying what a push runs); the demo path walked on staging with the user in light, dark and at phone width (the exit gate)

**Doc updates (concurrent)**
- [ ] Pages not redesigned to `BACKLOG.md`; `docs/tracking/SPRINT-AUDIT.md` (Rule C), `docs/handover/sprint-03-handover.md`, `ROADMAP.md`, `BACKLOG.md`

**Commit checkpoint**
- [ ] `docs: complete sprint 3 audit and handover`

### Alongside (not blocking)
- [ ] The user seeds the staging register with the quick add, gives the consultant directors the CDM role and processes calls from consultants told beforehand (who and when recorded here); each run reviewed (node errors, rejected quotes, cost, timing), any prompt fix as its own `fix:` commit; then the Phase 1 and Phase 2 exit gates (BACKLOG High Priority)
- [ ] A Teams admin confirms the chat RSC state and step A5 is run (`docs/integrations/TEAMS-GRAPH-SETUP.md`), so Sprint 4 can start

## Blockers and Dependencies
- Each page waits on the user's approval of its design; Phases 6 and 7 depend on the time left.
- The exit gates of PRD Phases 1 and 2 need real data on staging (the user's actions).

## Session State (last updated: 2026-10-12 12:52)
- **Sprint**: 3 — Visual Redesign
- **Current phase**: Phase 0
- **Phase progress**: plan approved and written; commit not yet made
- **Last completed task**: Sprint 3 planned with the user (2026-10-12)
- **Next task**: commit `docs: plan sprint 3` (with the user's go-ahead), then Phase 1: create the Stitch project and design system and generate the token-sheet variants for approval
- **Last commit**: 9a2963f "docs: record the cdm deploy and plan the redesign"
- **Uncommitted changes**: this file, `planning/ROADMAP.md`, `planning/BACKLOG.md`
- **Blockers**: none
- **Tests passing**: 763 unit + 282 integration (backend) + 202 frontend unit (`--maxWorkers=4`) + 21 e2e = 1268 (Sprint 2 close; not re-run, nothing changed since)
- **Files modified this session**: `docs/planning/{CURRENT-SPRINT,ROADMAP,BACKLOG}.md`
- **Key decisions this session**: the 17 planning decisions above (2026-10-12)
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-02-handover.md`.
  - **Stitch**: its tools load only in a session started after it was connected (user scope); check they are listed before relying on them. The PMO project is created in Phase 1; record its id here.
  - **Local stack**: `docker compose up --build -d --wait`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS sign-in**: `aws sso login --profile pmo-intelligence`. Nothing is ever deleted or overwritten in the main ITC account (`430006376054`).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Carried from Sprint 2: the Phase 1 and Phase 2 exit gates are in BACKLOG High Priority, and placements are entered on Admin > Register or with the quick add (the CSV import was removed) | User decisions 2026-10-11 (Sprint 2 Decisions Log, in git history) |
| Carried from Sprint 2: the redesign's landing page is the sign-in page as a showcase (not a public marketing page), in a neutral modern SaaS style with a dark hero, not the ITC brand; the preview uses made-up data only; screenshots for design reference come from the local stack's seeded data, never staging | User decisions 2026-10-11 (BACKLOG) |
| Every row of "User Decisions Made" above | User decisions 2026-10-12, Sprint 3 planning; alternatives listed with each |
