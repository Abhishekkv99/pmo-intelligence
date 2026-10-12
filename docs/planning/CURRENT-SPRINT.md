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
| Design direction (Phase 1, after four plain token sheets were judged not modern enough and a research pass on Superhuman, Linear, Raycast and 2026 dashboard trends) | **Twilight** (Superhuman-like): a deep twilight gradient hero (#1B1938 → #4C326E → #794B7A → dusk) dissolving into warm white #FBFAF8; huge display type (line-height 0.96, tight tracking); lavender #CBB7FB accent, cream #E9E5DD sign-in button, charcoal #292827 text, warm grey #DCD7D3 hairlines; a large product screenshot; status red #DC2626, amber #D97706, green #16A34A. Replaces: indigo accent; "always dark" sign-in (it is now dark into light) | Aurora (Linear-like, dark, 3D board); Command centre (Raycast-like bento) and a mix of the two with Twilight's chart |
| Font (Phase 1) | Plus Jakarta Sans for text, JetBrains Mono for numbers, as in Twilight. Replaces: keep Geist | Keep Geist |
| Theme (Phase 1) | The app opens in the light Twilight theme; a twilight-dark theme (deep purple surfaces, lavender accents) stays in the theme menu with system, so every page still supports dark mode | Follow the system |
| Shell design (Phase 1) | Stitch draws the signed-in shell and risk board in both themes for approval before tokens are written | Derive the tokens from Twilight without a further screen |
| Judgement calls made while building Phase 1 (for approval at the checkpoint) | Contrast over the mockups' exact values: muted text #66635F (the mockup's #85817B is 3.7:1), green #15803D (the mockup's #16A34A is 3.3:1 as text), amber kept as a fill with dark text (#D97706 is 3.2:1 as text). `--radius` 0.75rem: cards 16px as in Twilight, buttons and inputs 10px (Twilight 8px). Focus ring plum #794B7A in light, lavender in dark. Chart line `--chart-1` #4C326E in light, lavender in dark. The sidebar is twilight purple in both themes through the sidebar tokens; the current sidebar got one class (`text-sidebar-foreground`) so its title stays readable until Phase 2 replaces it. The logo is a client component so each mark gets its own gradient id (`useId`); the wordmark's mark is decorative. `--lavender`, `--twilight` and `--gradient-twilight` added as brand tokens |
| Sign-in design (Phase 3) | Stitch variant 3, "Twilight Sign-in (Variant 3: Two-Column Split Preview)" (`993d6e9bb3ff47089a97890d72e7b361`): the promise and "Sign in with Microsoft" on the left, a three-row risk board card over a flag card with its quote on the right, in the twilight hero; the three highlights and the footer on warm white below. The preview uses the app's own pieces: the health badge with the level in words, the real trigger name ("Client dissatisfaction", critical) and a "Sample data" tag in place of "Live Status". No chart (the plan's mini chart dropped). The phone layout stacks (promise, button, cards, highlights) and is reviewed in the browser, with no Stitch phone screen. The page always looks as designed, whatever the theme (a light token scope inside a dark theme; the theme setting never changed), and the callback page uses the same shell | Variant 1 (risk board preview), variant 2 (placement page preview); bare-number badges, "Early warning flag", "Live Status"; a mini chart card; a Stitch phone screen first; the lower part following the theme |
| Risk board design (Phase 4) | Stitch variant 2, "Risk Board (Variant 2: Grouped Level Sections)" (`51a5144a2ce3454dbdb045ee3e9901e1`): the heading with the subtitle "Every active placement, most at risk first.", a summary strip of four level counts, the filter bar, then one section per level (Red, Amber, Green, Not scored), each a card headed by the level's dot, the level and its count, with its own table. The headings say the level and count only: the screen's subtitles ("Immediate attention required", "Stable performance", and "Initial onboarding · baseline pending", which is wrong: not scored means no signal in the lookback) are dropped, and no thresholds are shown (the board's response carries none). The counts are buttons that filter the board: a click shows only that level and sets the level menu to match, a second click clears it; they count every row before the other filters and the search; a section with no rows is hidden. An SME sees one plain table (no strip, no sections), with the subtitle "Every placement you support, lowest Technical score first." Risk board keeps the `Gauge` icon and Admin its icon (the screen's dollar sign and missing icon are not the shell) | Variant 1 (coloured left edge), variant 3 (dense table, large score); subtitles of our own; live counts that follow the filters; counts for display only; the SME view as today |
| Judgement calls made while building Phase 4 (approved with the commit, 2026-10-12) | "No placements match these filters." when filters or the search hide every row (the empty board keeps its message); the section's level word in the text colour with only the dot coloured (amber text fails contrast on white); the health badge's score in mono, on the placement page too; the table restyle (muted header row, more padding) in every `DataTable`, Admin and Sessions included; the page title at the Twilight 32px; a level count of 0 still filters, showing the no-match message | — |
| Copy on the showcase | Every claim is ours and true: no compliance badges (SOC 2, ISO), no "encrypted end-to-end", no client email ingestion, no automatic notification or "playbook", no invented counts or versions; the generated screens' copy is a reference only | — (found in the generated screens) |
| Shell details (Phase 2, from the approved Twilight screen) | The top bar shows the sidebar toggle, the current section as a breadcrumb ("Risk board"; "Risk board / Placement" and "Sessions / Session" on a detail page, the parent a link) and the theme menu; "PMO Intelligence" is in the sidebar logo only, and `auth.spec.ts`'s header test changes with it. Risk board's icon is lucide `Gauge` (the screen's dollar sign reads as money); Sessions, Actions, Admin and Settings follow the screen (message, check-square, grid, gear). No subtitle under the product name (the screen's "v3.4 · Telemetry" is invented). The screen's "Jump to consultant" search goes to BACKLOG; no new Stitch variants, the approved screen is the shell design | As planned (the h1 "PMO Intelligence" in the top bar); section name and a working search; icons LayoutDashboard, ShieldAlert or Activity; the tagline as a subtitle |

## Task Checklist

>>> CURRENT PHASE: Phase 4 (next: commit checkpoint, then push with Phase 3)

Every phase: the Stitch step (variants on made-up data; the user picks one or asks for edits), then code, tests and docs, then the commit checkpoint, then stop. Any screenshot used for design reference comes from the local stack seeded with `seed_e2e_session.py --health`, never from staging. Before e2e: `docker compose up --build -d --wait frontend`, one worker; Vitest with `--maxWorkers=4`.

### Phase 0: Plan
**Code work**
- [x] Plan approved (2026-10-12)

**Doc updates (concurrent)**
- [x] This file; `ROADMAP.md` (a Sprint 3 section; Milestone 3 marked for Sprint 4); `BACKLOG.md` (the redesign item in progress)

**Commit checkpoint**
- [x] `docs: plan sprint 3` (be6231b, 2026-10-12; not pushed)

### Phase 1: Design system, tokens, logo and motion
**Code work**
- [x] Stitch: project "PMO Intelligence" (`15166762438523107418`) and a first design system (indigo, Geist); token sheets in four colour treatments, judged not modern enough by the user; three showcase directions after research (Aurora, Twilight, Command centre); **Twilight chosen** (2026-10-12; deviation from the planned token sheet, see the Decisions Log)
- [x] Stitch: the signed-in shell and risk board in the light and twilight-dark themes, side by side ("Twilight Light & Dark Risk Board Comparison"); approved 2026-10-12 without its invented parts (Export CSV, Telemetry Sync, version text, nav counts)
- [x] `src/app/globals.css`: the Twilight values as oklch, light (warm white, charcoal, twilight purple, lavender, cream) and twilight-dark, under the existing token names; a twilight hero gradient token; `--risk-*` from Twilight's status colours; a `prefers-reduced-motion` block for `.chart-animate`
- [x] Fonts: Plus Jakarta Sans and JetBrains Mono through `next/font/google` in `src/app/layout.tsx` (replacing Geist), its test mock updated; the theme opens light (`defaultTheme`), with twilight-dark and system in the theme menu
- [x] `src/components/brand/Logo.tsx` (`LogoMark`: a lavender pulse line in a deep-purple rounded square, as in Twilight; `Wordmark`); `src/app/icon.svg`, `src/app/favicon.ico` deleted
- [x] `src/proxy.ts` matcher passes `icon.svg`
- [x] `pnpm add motion@13.4.6 --save-exact`; `src/components/providers/MotionProvider.tsx` (`MotionConfig reducedMotion="user"`) in `src/app/layout.tsx`
- [x] Tests: `Logo.test.tsx` (4); `layout.test.tsx` (+1, the motion settings; the font mock follows the new fonts); `src/proxy.test.ts` (8). Frontend unit 215 with `--maxWorkers=4`; lint, types and format clean; e2e 20 of 21 with one worker (the known `sessions.spec.ts` recording race, BACKLOG; 2 of 3 alone); screenshots of the board, placement page and login in both themes checked

**Doc updates (concurrent)**
- [x] `docs/DESIGN.md` (new: tokens, contrast, logo, motion rules), `ARCHITECTURE.md` (root layout, generic UI, `> Status:`), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (also `BACKLOG.md`: the e2e race seen with one worker; README: no new make target; ROADMAP: nothing ticked until the shell lands)

**Commit checkpoint**
- [x] `feat: add the design tokens, logo and motion setup` (31700ab, 2026-10-12; not pushed; the Phase 1 judgement calls approved with the commit)

### Phase 2: App shell
**Code work**
- [x] Stitch: no new variants; the approved "Twilight Light & Dark Risk Board Comparison" screen is the shell design (user decision 2026-10-12; its gaps settled in the Decisions table, "Shell details")
- [x] `pnpm exec shadcn add sidebar` (existing ui files kept; `globals.css` unchanged), and `breadcrumb` and `avatar` for the top bar and the user menu. The CLI (3.8.4) wrote `import { cn } from "cn"` into each new file and added the unrelated npm package `cn`; the imports were pointed at `@/lib/utils` and the package removed (deviation). `SidebarMenuSkeleton`'s random width made fixed (the purity lint rule refuses `Math.random`; unused here)
- [x] `src/components/layout/nav.ts`: the nav items with lucide icons, `visibleNavItems` and `getActiveHref` moved from `Sidebar.tsx`; Risk board active on `/placements/*` (fixes the Sprint 2 known issue)
- [x] `src/components/layout/AppSidebar.tsx`: logo link (not a heading), nav with tooltips, `collapsible="icon"`, rail, user menu with sign-out in the footer
- [x] `MainLayout.tsx`: `SidebarProvider` from the cookie, `SidebarInset`, the top bar (`SidebarTrigger`, the section breadcrumb, `ThemeToggle`; see "Shell details"); `Sidebar.tsx` and `Header.tsx` removed once merged; the top bar is `TopBar.tsx`
- [x] Route group `src/app/(app)/layout.tsx`: `/`, `sessions`, `sessions/[sessionId]`, `placements/[placementId]`, `admin`, `actions`, `settings` moved under it, their own `MainLayout` wrappers removed
- [x] Tests: `Sidebar.test.tsx` → `nav.test.ts` (same labels and href, plus the active item and the breadcrumb: 17); `AppSidebar.test.tsx` (active item, Admin hidden for other roles, placement path active, the user menu signs out: 12); `TopBar.test.tsx` (4); a `matchMedia` stub in `src/test/setup.ts`; `auth.spec.ts`: the app-name heading test now checks the logo link and the breadcrumb, plus the rail kept across a reload and the phone drawer (+2). Frontend unit 245 with `--maxWorkers=4`; e2e 23 of 23 with one worker; screenshots in light, dark, the icon rail and at phone width checked (the logo mark was shrunk to 16px by the menu button and fixed)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (Shell and Pages rows with the new paths, `> Status:`), `DESIGN.md` (shell), `FEATURES.md`, `TESTS.md`, `CHANGELOG.md` (also `ROADMAP.md`: the design system, logo and shell ticked; `BACKLOG.md`: the top-bar search; README: no new make target)

**Commit checkpoint**
- [x] `feat: add the collapsible app shell` (88f83e2, 2026-10-12; pushed with be6231b and 31700ab, CI green, frontend deployed)

### Phase 3: Sign-in showcase and callback
**Code work**
- [x] Stitch: 3 desktop variants with made-up placements and our own copy; the user chose variant 3 (2026-10-12); the phone layout is reviewed in the browser (see "Sign-in design")
- [x] `src/components/auth/AuthShell.tsx` (the full-viewport frame with the logo; always light, not forced dark, per "Sign-in design"), `Showcase.tsx` (the promise, "calls and chat in, health and early warnings out", 3–4 highlights, a motion entrance), `MiniRiskBoard.tsx` (`HealthIndicators`; no mini chart, per "Sign-in design"), `showcase-data.ts` (fixed ISO dates, typed against `types/health.ts`, plainly made up)
- [x] `LoginForm.tsx` restyled (the button keeps its text; the Entra note follows the approved design, "Staff with a role only · Microsoft Entra ID", under the test-text decision; its test still matches); `src/app/login/page.tsx`; the callback page inside `AuthShell`; `APP_TAGLINE` only if the approved copy changes it
- [x] Tests: `Showcase.test.tsx` (9: the sample rows, the sample tag, the flag, the highlights, no request, the light frame, the UK time); `LoginForm.test.tsx` and the callback `page.test.tsx` unchanged (their text is kept or still matched); `auth.spec.ts` checks the promise heading and the sample tag in place of the "Sign In" card title. Frontend unit 254 (`--maxWorkers=4`, every row compared with `vitest list`), lint, types, format clean; screenshots at desktop, phone and under the dark theme setting, and the callback's failure, checked (from `next dev` on port 3100, which wrote `frontend/AGENTS.md`, now in `.git/info/exclude`). e2e 23 of 23 with one worker after Docker Desktop was force-restarted (it had answered every request with 500)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (a Sign-in row, auth flow step 1, `> Status:`), `DESIGN.md` (Sign-in, Theme), `FEATURES.md`, `TESTS.md` (unit rows; the e2e count after the run), `CHANGELOG.md` (also `ROADMAP.md`: the sign-in item ticked; BACKLOG: nothing new; README: no new make target)

**Commit checkpoint**
- [x] `feat: add the sign-in showcase` (7576cda, 2026-10-12; not pushed)

### Phase 4: Risk board
**Code work**
- [x] Stitch: 3 variants, light and dark, 12 made-up rows, the filter bar and the summary strip; the user chose variant 2, grouped level sections (2026-10-12; see "Risk board design")
- [x] `RiskBoard.tsx` (the level counts as filter buttons, the filter bar card with its own search, a section per level, wrapping client · project and next action; the server's order, the filters and the SME view kept, the SME as one table), `HealthIndicators.tsx` (`health-badge` kept, the score in mono), `DataTable.tsx` (`searchable` and `framed` options, the muted header row, cell padding); the page keeps its h2 "Risk board" at the Twilight title size
- [x] Tests: `RiskBoard.test.tsx` (11 → 15: sections, counts, count filter and clear, search; the SME without counts or sections); `DataTable.test.tsx` (4 → 6); `risk-board.spec.ts` (the Amber section, the Green count). Frontend unit 260 with `--maxWorkers=4` (every row compared with `vitest list`); lint, types (after `next typegen` refreshed stale `.next/types`), format clean; e2e 23 of 23 with one worker against the rebuilt frontend; screenshots in light and dark at 1440px checked (the filter bar wrapped and the next action ran off the card; fixed)

**Doc updates (concurrent)**
- [x] `ARCHITECTURE.md` (Risk board and Tables rows, `> Status:`), `DESIGN.md` (Tables and badges, Risk board, status), `FEATURES.md` (a new row; the risk board page's path moved to `(app)/`), `TESTS.md`, `CHANGELOG.md` (ROADMAP: nothing ticked until the placement page; BACKLOG: nothing new; README: no new make target)

**Commit checkpoint**
- [ ] `feat: redesign the risk board` (with the push of 7576cda and this commit, user decision 2026-10-12)

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

## Session State (last updated: 2026-10-12 21:10)
- **Sprint**: 3 — Visual Redesign
- **Current phase**: Phase 4 — risk board (built, awaiting the commit checkpoint)
- **Phase progress**: Phase 3 complete and committed; Phase 4 4 of 5 (commit left)
- **Last completed task**: Phase 4 code, tests and docs (the approved variant 2, grouped level sections)
- **Next task**: the user approves the Phase 4 judgement calls and the commit `feat: redesign the risk board`; then push 7576cda and it together (frontend only: read both CI filters first), watch CI and the frontend deploy; then Phase 5 (placement page variants in Stitch) at the user's go-ahead
- **Last commit**: 7576cda "feat: add the sign-in showcase" (local, not pushed); before it 88f83e2, pushed 2026-10-12 with CI green and the frontend deployed
- **Uncommitted changes**: Phase 4: `frontend/src/components/health/{RiskBoard,RiskBoard.test,HealthIndicators}.tsx`, `frontend/src/components/common/{DataTable,DataTable.test}.tsx`, `frontend/src/app/(app)/page.tsx`, `frontend/tests/e2e/risk-board.spec.ts`, `docs/{ARCHITECTURE,DESIGN}.md`, `docs/tracking/{TESTS,FEATURES,CHANGELOG}.md`, this file
- **Blockers**: none
- **Tests passing**: 763 unit + 282 integration (backend, unchanged since 2026-10-11) + 260 frontend unit (`--maxWorkers=4`); 23 of 23 e2e (one worker) = 1328 tests
- **Files modified this session**: the uncommitted changes above
- **Key decisions this session**: the 17 planning decisions above; in Phase 1 the Twilight direction, Plus Jakarta Sans and JetBrains Mono, a light default with a twilight-dark theme, the shell screen before tokens, and our own copy only (Decisions Log rows, 2026-10-12); in Phase 2 build the shell from the approved screen with no new variants, the section breadcrumb instead of the app name in the top bar (search to BACKLOG), `Gauge` for Risk board, no subtitle, push with Phase 2 ("Shell details" row)
- **Recovery instructions**:
  - Read this file first, then `docs/handover/sprint-02-handover.md`.
  - **Stitch**: its tools load only in a session started after it was connected (user scope); check they are listed before relying on them. The PMO project is `15166762438523107418` ("PMO Intelligence"); the chosen direction is the screen "PMO Intelligence — Twilight Sign-in Showcase". Generation calls time out on this side after about a minute but finish in Stitch 10–40 minutes later; poll `list_screens` instead of re-sending
  - **Local stack**: `docker compose up --build -d --wait`, `make migrate`, `make test-e2e`. Add `PMO_API_PORT=8100 PMO_WEB_PORT=3100` when another project holds ports 8000/3000.
  - **Push and `gh`**: use `Abhishekkv99`'s token per command, never a change to the default login: `git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$(gh auth token --user Abhishekkv99)"; }; f' push origin develop`.
  - **AWS sign-in**: `aws sso login --profile pmo-intelligence`. Nothing is ever deleted or overwritten in the main ITC account (`430006376054`).

## Decisions Log
| Decision | Rationale |
|----------|-----------|
| Carried from Sprint 2: the Phase 1 and Phase 2 exit gates are in BACKLOG High Priority, and placements are entered on Admin > Register or with the quick add (the CSV import was removed) | User decisions 2026-10-11 (Sprint 2 Decisions Log, in git history) |
| Carried from Sprint 2: the redesign's landing page is the sign-in page as a showcase (not a public marketing page), in a neutral modern SaaS style with a dark hero, not the ITC brand; the preview uses made-up data only; screenshots for design reference come from the local stack's seeded data, never staging | User decisions 2026-10-11 (BACKLOG) |
| Every row of "User Decisions Made" above | User decisions 2026-10-12, Sprint 3 planning; alternatives listed with each |
