# Sprint 03 Handover Document

**Sprint Duration**: 2026-10-12 - 2026-10-13 (planned 2026-10-12 – 2026-10-23; every phase built, the "if time" ones included, and closed early)
**Sprint Objective**: a modern, management-ready look, designed page by page in Google Stitch and approved before each page was built: the design system, the app shell, a showcase sign-in page, the risk board and the placement page first, then the sessions pages and Admin. Not a PRD phase; moved ahead of Teams chat (PRD Phase 3) so the tool can be demonstrated.
**Audit Status**: PASSED — see `docs/tracking/SPRINT-AUDIT.md`

> **GATE**: This handover can ONLY be created AFTER the sprint audit is complete.

**Exit gate: met 2026-10-13.** The user walked the sign-in page, the shell, the risk board and a placement page on staging, in light and dark, with sign-in and the shell at phone width, and approved them. Staging had no placements, so five were entered with the quick add first; they show as Not scored, since no real call has been processed, so the chart, flags and contributors were judged on the local stack's seeded data during the build, not on staging. One change was asked for and went to BACKLOG (the risk board's project in its own column).

## 1. What Was Achieved
- **Design system** (Phase 1, 31700ab): the Twilight look in `frontend/src/app/globals.css` (a warm white light theme, the default, and a twilight-dark theme; every colour pair checked for AA; the RAG colours as tokens; a twilight hero gradient), Plus Jakarta Sans and JetBrains Mono in `frontend/src/app/layout.tsx`, the logo (`frontend/src/components/brand/Logo.tsx`) and browser icon (`frontend/src/app/icon.svg`, replacing `favicon.ico`; `frontend/src/proxy.ts` lets it through), and motion that follows the reader's reduced-motion setting (`frontend/src/components/providers/MotionProvider.tsx`, `motion` 13.4.6). Written up in the new `docs/DESIGN.md`.
- **App shell** (Phase 2, 88f83e2): one layout for every signed-in page in the route group `frontend/src/app/(app)/` (URLs unchanged), with a collapsible sidebar (`frontend/src/components/layout/AppSidebar.tsx`: icons, an icon rail with tooltips kept in the `sidebar_state` cookie, a drawer on a phone, the user menu in its footer), a top bar with the section breadcrumb (`TopBar.tsx`) and the nav rules in `nav.ts`. Risk board is now active on a placement page (a Sprint 2 known issue).
- **Sign-in showcase** (Phase 3, 7576cda): `frontend/src/components/auth/{AuthShell,Showcase,MiniRiskBoard,showcase-data}.tsx`: the promise, "Sign in with Microsoft", a sample risk board and flag from made-up data (nothing is requested before sign-in), three highlights; always in the light theme; the callback page in the same frame.
- **Risk board** (Phase 4, 5ee6b1b): `frontend/src/components/health/RiskBoard.tsx`: level counts that filter the board, the filters in one bar, a section per level; an SME sees one plain table. `DataTable.tsx` gained `searchable`, `framed`, `dense` and `rowClassName`.
- **Placement page** (Phase 5, 8921f35): `PlacementHealthView.tsx` and its pieces: one header card with the six tiles, two columns (the actionable column first when stacked), each contributor's value beside its weight.
- **Sessions pages** (Phase 6, 039fc3a): `SessionsList.tsx` (dense rows, a dot status, a failed row tinted, one filter bar) and `SessionView.tsx` (the analysis on the left, the transcript in a column that stays in view, the recording in a card).
- **Admin, Actions and Settings** (Phase 7, 4a61ac2): `AdminView.tsx` (subtitle, underlined tabs), `RegisterTab.tsx` (filled sub-tabs), `EmptyState.tsx` (a dashed card with an icon, also on the not-found and no-access states), flat cards (`ui/card.tsx`).
- **Deploys**: each push deployed the frontend alone through CI (five runs, listed in the `docs/DEPLOYMENT.md` status line); the backend was never restarted.
- **Tests**: 1333 in all (763 backend unit, 282 integration, 265 frontend unit, 23 e2e), up from 1268 at the start of the sprint (frontend unit 202 → 265, e2e 21 → 23); per file in `docs/tracking/TESTS.md`.

## 2. What Was NOT Achieved
- **Real calls on staging and the PRD Phase 1 and 2 exit gates** (planned alongside, not blocking): no real call was processed this sprint. Still in BACKLOG, High Priority. The register now has five placements.
- **The Teams chat RSC check and step A5** (alongside, for Sprint 4): not done; it needs a Teams or Global admin. Still in BACKLOG, High Priority.
- **The top bar's "Jump to consultant" search** drawn on the approved shell screen: left out as a new feature (user decision 2026-10-12). BACKLOG, Medium Priority.
- **The risk board's project column**, asked for in the walk-through: BACKLOG, Medium Priority (user decision 2026-10-13: note changes as backlog items).
- Every page planned for redesign was redesigned; none moved to the backlog.

## 3. Decisions Made
Every decision with its alternatives is in the "User Decisions Made" table of `docs/planning/CURRENT-SPRINT.md` (in git history after the next sprint is planned). The ones that shape later work:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Twilight direction: a deep twilight gradient into warm white, a lavender accent, Plus Jakarta Sans and JetBrains Mono; the app opens light, with a twilight-dark theme in the menu | Four plain token sheets were judged not modern enough; chosen after research on Superhuman, Linear and Raycast | Aurora (dark, Linear-like), Command centre (Raycast-like bento); indigo on Geist |
| Each page designed in Stitch (2–3 variants on made-up data) and approved before code; the screens' HTML is a reference, rebuilt in the app's own components | Approval before building; no staging data ever sent to the design tool | Review in the browser only |
| The shadcn `sidebar` block, the route group `(app)` with one layout | The shell stays mounted; a phone drawer and icon rail come with the block | Restyle the old sidebar; a layout per page |
| The sign-in page always light, whatever the theme setting, with a light token scope and no portals | The page always looks as designed; the reader's setting is never changed | Always dark; follow the theme |
| Copy on the showcase is ours and true (no compliance badges, invented counts or automatic actions) | The generated screens invented claims | — |
| Contrast over the mockups' values (muted text #66635F, green #15803D, amber as a fill only) | AA for text and status colours | The mockups' exact values |
| RAG colours mean health only: no coloured call-kind pills or issue dots; level words in the text colour with a coloured dot | A colour should say one thing; amber text fails contrast on white | The screens' coloured pills |
| The browser's own `<audio controls>` kept, in a card | A custom player was not needed for the demo | A custom player |
| `motion` 13.4.6 pinned exactly, client components only | 14.x was a new major days old | CSS only; 14.1.0 |
| Exit gate on staging with the register seeded by the quick add (placements Not scored) | The page structure is what the gate judges; scores need a real call, which is separate work | Local screenshots for the data pages; hold the gate for a real call |

## 4. Files Created / Modified
| File | Action | Description |
|------|--------|-------------|
| `docs/DESIGN.md` | Created | Tokens, contrast, type, logo, shell, page patterns, motion |
| `frontend/src/app/(app)/layout.tsx` | Created | The signed-in layout (the shell) |
| `frontend/src/app/(app)/{page,actions/page,admin/page,sessions/page,settings/page}.tsx` | Created (moved) | The pages under the route group; `actions` and `settings` with subtitles and empty states |
| `frontend/src/app/(app)/sessions/[sessionId]/page.tsx`, `(app)/placements/[placementId]/page.tsx`, `(app)/admin/error.tsx` | Moved | From `frontend/src/app/` |
| `frontend/src/app/{page,actions/page,admin/page,sessions/page,settings/page}.tsx`, `frontend/src/app/favicon.ico` | Deleted | Replaced by the route group and `icon.svg` |
| `frontend/src/app/icon.svg` | Created | The browser icon |
| `frontend/src/app/globals.css` | Modified | Twilight tokens, light and dark; brand tokens; reduced-motion block |
| `frontend/src/app/layout.tsx`, `layout.test.tsx` | Modified | Fonts, light default theme, motion settings |
| `frontend/src/app/login/page.tsx`, `frontend/src/app/auth/callback/microsoft/page.tsx` | Modified | The showcase and the shared frame |
| `frontend/src/components/auth/{AuthShell,Showcase,MiniRiskBoard}.tsx`, `showcase-data.ts`, `Showcase.test.tsx` | Created | Sign-in showcase |
| `frontend/src/components/auth/LoginForm.tsx` | Modified | Restyled; the Entra note |
| `frontend/src/components/brand/Logo.tsx`, `Logo.test.tsx` | Created | `LogoMark`, `Wordmark` |
| `frontend/src/components/layout/{AppSidebar,TopBar}.tsx`, `nav.ts` and their tests | Created | The shell |
| `frontend/src/components/layout/{Sidebar,Header}.tsx`, `Sidebar.test.tsx` | Deleted | Replaced by the shell |
| `frontend/src/components/layout/MainLayout.tsx` | Modified | `SidebarProvider` from the cookie, `SidebarInset`, the top bar |
| `frontend/src/components/providers/MotionProvider.tsx` | Created | `MotionConfig reducedMotion="user"` |
| `frontend/src/components/ui/{sidebar,sheet,tooltip,avatar,breadcrumb}.tsx`, `frontend/src/hooks/use-mobile.ts` | Created | shadcn components (imports pointed at `@/lib/utils`) |
| `frontend/src/components/ui/card.tsx` | Modified | No default shadow |
| `frontend/src/components/health/{RiskBoard,PlacementHealthView,DimensionScores,FlagList,EvidenceItem,HealthIndicators}.tsx` and tests | Modified | Risk board and placement page |
| `frontend/src/components/sessions/{SessionsList,SessionView,SessionStatusBadge}.tsx`, `SessionsList.test.tsx` | Modified | Sessions pages |
| `frontend/src/components/admin/{AdminView,ProcessingStatusPanel}.tsx`, `AdminView.test.tsx`, `register/{RegisterTab,QuickAddCard}.tsx` | Modified | Admin |
| `frontend/src/components/common/{DataTable,EmptyState}.tsx` and tests | Modified | Table options; the dashed empty state with an icon |
| `frontend/src/proxy.ts`, `frontend/src/proxy.test.ts` | Modified, created | `icon.svg` passes the sign-in check |
| `frontend/src/test/setup.ts` | Modified | `matchMedia` stub |
| `frontend/tests/e2e/{auth,placement-health,risk-board,sessions}.spec.ts` | Modified | Shell, showcase, sections, contributor value, transcript column |
| `frontend/package.json`, `frontend/pnpm-lock.yaml` | Modified | `motion` 13.4.6 |
| `README.md`, `docs/{ARCHITECTURE,DEPLOYMENT}.md`, `docs/tracking/{CHANGELOG,FEATURES,TESTS,SPRINT-AUDIT}.md`, `docs/planning/{CURRENT-SPRINT,ROADMAP,BACKLOG}.md` | Modified | Kept current per phase; audit fixes |
| `docs/handover/sprint-03-handover.md` | Created | This document |

## 5. Environment Changes
- New dependencies: `motion` 13.4.6 (exact). The shadcn sidebar, sheet, tooltip, avatar and breadcrumb are source files, not packages.
- New environment variables: none.
- Configuration changes: the app opens in the light theme (`defaultTheme`); the sidebar's open state is kept in the `sidebar_state` cookie; fonts load through `next/font/google`.
- Infrastructure changes: none. Five frontend-only deploys by CI (see `docs/DEPLOYMENT.md`); no migration (009 remains the head).

## 6. Known Issues / Bugs
- `sessions.spec.ts` can fail locally (the seed's undecodable recording, and a timeout under parallel load); it passed 23 of 23 with one worker in the audit run. BACKLOG, Tech Debt (low).
- Frontend unit tests can pass Vitest's 5 s timeout with the default worker count on a loaded machine; run with `--maxWorkers=4`. BACKLOG, Tech Debt (low).
- The unused `.chart-animate` CSS in `globals.css`. BACKLOG, Tech Debt (low).
- The shadcn CLI (3.8.4) wrote `import { cn } from "cn"` into each component it added and installed an unrelated `cn` package; both were corrected. Check the imports after any future `shadcn add` (low).
- The staging placements show as Not scored until a real call is processed (expected, not a bug).

## 7. Learnings
### What Went Well
- Approving a Stitch variant before writing code kept every page to one build pass; the user's choices and the dropped parts of each screen are recorded per page.
- The rule that page headings, nav labels and test ids stay meant the e2e suite carried through a full redesign with small, deliberate changes.
- Frontend-only pushes never touched the backend, so processing was never interrupted.
- Screenshots from the local stack's seeded data caught layout problems before each commit (a wrapping filter bar, a mislaid kind label, a faint dashed outline).

### What Didn't Go Well
- `docs/DESIGN.md` was written from the mockups and the plan, and eleven values drifted from what was built (S3-4).
- Stitch generation calls time out on the client after about a minute and finish 10–40 minutes later; one round of Admin variants took about 45 minutes.
- A server page passed an icon component to a client component (React error 441), caught only by e2e; icons are now passed as elements.
- Moved page paths and the deploy record were not swept through the docs (S3-1, S3-3).

### Rules Added / Updated
Six sprint-workflow rules (local rules), each with a Learnings Log line: grep a moved file's old path in the docs; a new doc gets a README row; record every deploy in DEPLOYMENT's status; read DESIGN.md values back from the code; move a status line's head with its body; read changed doc lines whole before committing.

## 8. Post-Sprint Audit Findings
**Findings count**: 6
**Rules added**: 6

| What was wrong | Root cause | Rule added/updated |
|---------------|-----------|-------------------|
| FEATURES.md named the Sessions page at its pre-move path (S3-1) | Only the rows of the pages being redesigned were updated after the `(app)/` move | Sprint workflow: grep a moved file's old path in docs and README in the same commit |
| README's docs table missed `DESIGN.md` and `DEPLOYMENT.md` (S3-2) | Only make targets had a README rule | Sprint workflow: a new doc gets a README row in the same commit |
| DEPLOYMENT's status had none of the five Sprint 3 deploys (S3-3) | No infrastructure change, so DEPLOYMENT.md was in no doc list; deploy facts went only into the Session State | Sprint workflow: every deploy recorded in DEPLOYMENT's status in the next commit |
| Eleven DESIGN.md values differed from the code (S3-4) | Written from the mockup and plan, not read back after building | Sprint workflow: DESIGN.md values copied from the built classes and tokens |
| DESIGN.md's status line said Phase 4 (S3-5) | Phases appended to the body, the head never rewritten | Sprint workflow: a status line's head moves with its body |
| A duplicated phrase in ARCHITECTURE (S3-6) | An insertion was not read back whole | Sprint workflow: read changed doc lines whole with `git diff --word-diff` |

## 9. Next Sprint Recommendations
### Priority 1 (Must Do)
- **Sprint 4: Teams chat (PRD Phase 3, ROADMAP Milestone 3)**, planned with `/sprint-start`. Before it can start, a Teams or Global admin confirms the chat RSC state and step A5 is run (`docs/integrations/TEAMS-GRAPH-SETUP.md`); BACKLOG, High Priority. If that is still waiting at planning, decide whether to plan around it or swap in other work.
- **Process real calls on staging** from consultants told beforehand, review each run (node errors, rejected quotes, cost, timing) and run the PRD Phase 1 and Phase 2 exit gates; the register has five placements now, but a call from the recordings folder can be processed only when its folder is matched to a consultant and one of that consultant's placements covers the call's date (an upload or URL takes the placement directly).

### Priority 2 (Should Do)
- The risk board's project in its own column (from the walk-through).
- Give the CDMs, PSs and SMEs their roles and name them on the placements, so scoped views can be checked with real people.
- The `sessions.spec.ts` seed: a small decodable WebM, and the cold-start allowance on the retry test.

### Priority 3 (Nice to Have)
- The top bar's "Jump to consultant" search.
- Remove the unused `.chart-animate` CSS.
- Narrow the Teams app's availability to the PMO team (an admin action, BACKLOG High Priority).
