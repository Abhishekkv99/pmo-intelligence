# Design System

> **Status**: Sprint 3 Phase 4 (2026-10-12): the Twilight direction, its light and twilight-dark colours, fonts, logo and motion settings (Phase 1), the app shell (Phase 2), the sign-in showcase (Phase 3), the risk board (Phase 4) and the placement page (Phase 5) are built. The redesigned pages follow phase by phase; each section below says what is built.

PMO Intelligence is shown to management, so it should look like a premium product while staying calm and dense enough for daily PMO work. The look is called **Twilight**. It is editorial and Superhuman-like: one dramatic twilight-purple moment on a warm white canvas, large tight display type, a single lavender accent, and the product's own screens as the main imagery. Colour signals status; it never decorates.

Designs are made in Google Stitch (project "PMO Intelligence") from text descriptions with made-up data only. Each page's design is approved before it is built, then rebuilt in the app's own components (shadcn/ui and the tokens below). The generated HTML is a reference, never pasted in.

## Colour
All colours are CSS variables in `frontend/src/app/globals.css`, in oklch, light under `:root` and dark under `.dark`, with the hex they came from in a comment. Components use the token names (`bg-primary`, `text-muted-foreground`, `bg-risk-red`), never a raw colour. The one exception is the logo, whose colours are fixed so it reads the same everywhere.

### Light (the default theme)
| Token | Hex | Role |
|-------|-----|------|
| `--background` | #FBFAF8 | Warm white canvas |
| `--foreground` | #292827 | Charcoal text |
| `--card`, `--popover` | #FFFFFF | Surfaces |
| `--primary` | #1B1938 | Deep twilight: primary actions, white text |
| `--secondary` | #E9E5DD | Cream: secondary actions |
| `--muted` | #F4F1EC | Quiet surfaces |
| `--muted-foreground` | #66635F | Secondary text |
| `--accent` | #F3EFE7 | Hover and selected rows |
| `--border` / `--input` | #E5E0D8 / #DCD7D3 | Hairlines |
| `--ring` | #794B7A | Focus (plum) |
| `--destructive` | #DC2626 | Destructive actions |

### Twilight dark
| Token | Hex | Role |
|-------|-----|------|
| `--background` | #121026 | Deep twilight canvas |
| `--foreground` | #F4F1EC | Warm white text |
| `--card`, `--popover` | #1B1938 | Surfaces |
| `--primary` | #CBB7FB | Lavender: primary actions, deep purple text |
| `--secondary` | #2A214C | Secondary actions |
| `--muted` | #14122B | Quiet surfaces |
| `--muted-foreground` | #A9A3B8 | Secondary text |
| `--accent` | #25224E | Hover and selected rows |
| `--border` / `--input` | lavender at 12% / 18% | Hairlines |
| `--ring` | #CBB7FB | Focus |
| `--destructive` | #F87171 | Destructive actions |

### Sidebar
The sidebar is the one dramatic colour in the app: twilight purple in both themes (#1B1938 light, #0D0B1E dark), warm white text, a lavender-tinted pill (lavender at 16%) for the active item, and #2A214C on hover.

### Brand
- `--lavender` (#CBB7FB): the single accent (`text-lavender`, `bg-lavender`).
- `--twilight` (#1B1938): the deep purple (`bg-twilight`).
- `--gradient-twilight`: the hero, from #1B1938 through #2A214C, #4C326E, #794B7A and dusk pinks (#A8687E, #D89A8F, #F3D6C9) into the canvas #FBFAF8. Used on the sign-in page only.

### Health (RAG)
`--risk-red`, `--risk-amber`, `--risk-green`, each with a `-foreground`. They mean health level and nothing else. Each is used both as a fill (badges) and as text (trend arrows, overdue dates), so each must pass 4.5:1 both ways.

| Level | Light | Dark | Fill text |
|-------|-------|------|-----------|
| Red | #DC2626 | #F87171 | white in light; #121026 in dark |
| Amber | #D97706 | #FBBF24 | #292827 in light; #121026 in dark |
| Green | #15803D | #4ADE80 | white in light; #121026 in dark |

The Twilight mockups used green #16A34A and amber #D97706 as text on white; those reach only 3.3:1 and 3.2:1, so green is #15803D and amber appears as a fill with dark text.

### Contrast checks
Computed with the WCAG 2 relative-luminance formula; every pair in use passes AA (4.5:1) for normal text.

| Pair | Ratio |
|------|-------|
| Charcoal on canvas (light) | 14.1 |
| Muted #66635F on canvas / on muted (light) | 5.7 / 5.3 |
| White on primary #1B1938 | 16.9 |
| Charcoal on cream #E9E5DD | 11.7 |
| #DC2626 and white, either way | 4.8 |
| #15803D and white, either way | 5.0 |
| Charcoal on #D97706 | 4.6 |
| Warm white on canvas (dark) | 16.5 |
| Muted #A9A3B8 on canvas / card / sidebar (dark) | 7.6 / 6.9 / 8.0 |
| #1B1938 on lavender | 9.4 |
| #F87171 / #4ADE80 / #FBBF24 on card (dark) | 6.1 / 9.7 / 10.1 |

## Type
- **Plus Jakarta Sans** for all text and **JetBrains Mono** for numbers (scores, deltas, counts), loaded through `next/font/google` in `frontend/src/app/layout.tsx` as `--font-plus-jakarta` and `--font-jetbrains-mono`, and mapped to Tailwind's `font-sans` and `font-mono`.
- Display (sign-in hero): up to 76px, line-height 0.96, tracking −0.035em. Page titles: 32px semibold, tracking −0.02em. Body 14–15px. Labels 11–12px; small caps labels are tracked out (0.2em).
- Numbers in tables use `font-mono tabular-nums`.

## Shape and depth
- `--radius` is 0.75rem: cards 16px (`rounded-xl`), buttons and inputs 10px (`rounded-md`), status pills fully round.
- Surfaces are flat with a 1px hairline border. The one large shadow is the editorial shadow under a product screenshot on the sign-in page.

## Logo
`frontend/src/components/brand/Logo.tsx`:
- `LogoMark`: a 40px rounded square (radius 12) in #2D2152 with a #805AD5 sheen and a #644B9E hairline, holding a lavender (#CBB7FB) pulse line. It is an image named "PMO Intelligence", or hidden from assistive technology when `decorative`.
- `Wordmark`: the decorative mark beside "PMO Intelligence" in bold. It is not a heading, so each page's headings stay its own.
- The favicon, `frontend/src/app/icon.svg`, is the same mark; the proxy lets `/icon.svg` through without a sign-in.

## Theme
The app opens in the light theme (`defaultTheme="light"`); twilight dark and the system setting are in the theme menu. Every signed-in page works in both. The sign-in and callback pages always show the light theme: their frame carries `theme-light`, which re-declares the light tokens (with `color-scheme: light`), and the `dark:` variant does not apply inside it. The theme setting itself is never changed.

## Shell
Built in Phase 2 from the approved Stitch screen "Twilight Light & Dark Risk Board Comparison", without its invented parts (version text, nav counts, Export CSV, Telemetry Sync, the "Jump to consultant" search).

- **Sidebar** (`frontend/src/components/layout/AppSidebar.tsx`, on shadcn's `sidebar`): the logo mark and "PMO Intelligence" as a link to the risk board (a link, not a heading); a "Navigation" group label in small mono capitals; one lucide icon per item (Risk board `Gauge`, Sessions `MessageSquare`, Actions `SquareCheck`, Admin `LayoutGrid`, Settings `Settings`); the user in the footer (initials on lavender, name, role), whose menu shows the email and Sign out.
- **Active item**: the lavender-tinted pill (`--sidebar-primary`, lavender at 16%) with lavender text and a lavender hairline at 25%; the others warm white at 75%. A placement page keeps Risk board active.
- **Collapsing**: the toggle in the top bar, or the rail along the sidebar's edge, folds it to a 48px icon rail where each item shows its name in a tooltip. The state is kept in the `sidebar_state` cookie for a week and read on the server, so a page renders as it was left.
- **Phone** (below 768px): the sidebar is a drawer from the left, opened by the toggle; following a link closes it.
- **Top bar** (`TopBar.tsx`): 56px, sticky, the canvas at 90% with a backdrop blur and a hairline below; the toggle, the breadcrumb (the section, then "Placement" or "Session" on a detail page with the section as a link) and the theme menu. Nothing in it is a heading; each page's heading is its own.
- **Layout**: the signed-in pages sit in the route group `frontend/src/app/(app)/`, whose layout renders `MainLayout` once, so the shell stays mounted between pages. `<main>` is the scroll container; the page has 16px padding on a phone and 24px from 768px.
- The sidebar is flat twilight purple; the screen's light-theme gradient (#1B1938 to #2A214C) was left out, since the sidebar's surface is one token in both themes.

## Sign-in
Built in Phase 3 from the approved Stitch screen "Twilight Sign-in (Variant 3: Two-Column Split Preview)".

- **Frame** (`AuthShell`): the twilight gradient (`--gradient-twilight`) behind the logo and the hero, dissolving into the warm white canvas; content up to 1240px wide; a hairline above the footer, which names the product and says "Internal tool." ("Sample data shown." on the login page).
- **Hero**: a lavender mono eyebrow ("Placement health, live"); the promise as the `h1`, white, `clamp(40px, 4.4vw, 62px)`, line-height 0.98, tracking −0.035em; the line under it white at 80%; the cream "Sign in with Microsoft" button (#E9E5DD, twilight text, Microsoft's four-square mark, a soft drop shadow, a 2px lift on hover unless reduced motion is on); the note under it white at 70%.
- **Preview** (`MiniRiskBoard`): two cards with the editorial shadow (`shadow-editorial`). The board card has a mono capitals header and a "Sample data" tag, then three rows with the app's own trend and health badge (score and level word). The flag card is tinted with the red at 5%, with a 2px red hairline at 25%, the trigger name and its severity, the quote with a red rule, and when it was said ("12 Sep · 14:32", UK time, months named by the code so every browser shows the same).
- **Highlights**: three columns between hairlines on the canvas (one column on a phone), each a 24px bold title and a muted paragraph.
- **Phone**: below 1024px the hero stacks (promise, button, preview), with 16px side gutters; a long name wraps instead of being cut.
- **Entrance**: each hero block rises 12px into place over 0.5s, 50ms apart; reduced motion keeps only the fade.
- The screen's "Live Status", bare-number badges and "Early warning flag" were replaced with the sample tag, the app's badge and the real trigger name.

## Tables and badges
- **Tables** (`DataTable`): a card (16px radius, hairline border, the card surface) holding the table; the header row on the muted surface with 12px semibold muted labels; cells 12px tall padding with 16px at the row's ends; numbers in `font-mono tabular-nums`. Inside another card the table drops its own frame (`framed={false}`).
- **Health badge**: a fully round pill in the level's colour with the score in JetBrains Mono and the level word ("6.3 Amber"); "Not scored" in muted text without a pill.
- **Flag chips**: a critical flag is a red pill with white text; any other is an outline pill. The name is the trigger's own, and the severity and opening date are in its tooltip.
- **Trend**: an arrow and the change over 14 days in mono, red when falling and green when rising; a dash before there is a score 14 days back.

## Risk board
Built in Phase 4 from the approved Stitch screen "Risk Board (Variant 2: Grouped Level Sections)".

- **Heading**: the page title "Risk board" (32px semibold, tracking −0.02em) and one muted line under it: "Every active placement, most at risk first."
- **Level counts**: four cards in a row (two on a phone), each a coloured dot, the level and its count in large mono. They count the whole board, whatever the filters; each is a button that shows only its level and sets the level menu to match, and a pressed card has a primary ring. A second click clears it.
- **Filter bar**: one card holding the search and the menus (placement specialist, CDM, client, stack, level), each menu as wide as its text, so the bar fits on one line at desktop widths.
- **Sections**: one card per level in the server's order (Red, Amber, Green, Not scored): a header strip tinted with the level's colour at 5% over a hairline at 20% (the card's edge at 30%), with the dot, the level as a heading in the text colour and the row count in a small mono tag; then the table. Not scored uses the muted surface and a grey dot. A level with no rows is not shown.
- **Rows**: client · project and the next action wrap over up to two lines rather than widen the table; the due date sits above the action in mono, red with "· overdue" when past.
- **SME**: one table with the same styling, no counts and no sections, under "Every placement you support, lowest Technical score first."
- The screen's subtitles on the sections ("Immediate attention required", "Elevated monitoring", "Stable performance", "Initial onboarding · baseline pending") were left out: they were invented, and not scored means no signal in the lookback, not onboarding. No thresholds are shown, since the board's response carries none. Level labels are in the text colour rather than the level's colour, since amber text fails contrast on white.

## Placement page
Built in Phase 5 from the approved Stitch screen "Placement: Priya Raman (Variant 1: Executive KPI Banner & Dual-Column Cockpit)".

- **Header card**: the back link "← Risk board" above it; inside, the consultant's name as the page title (32px semibold), the health badge, the trend and the status pill; client · project · weeks in; the register fields in one line; the scoring line in small mono, at the top right on a desktop; then the six score tiles.
- **Score tiles**: six across on a desktop (three on a tablet, two on a phone), each a card tinted with its level's colour at 5% over an edge at 40–50%, the dimension, the score in large mono and a line with the level's dot, the level word and the signal count. An SME sees the Technical tile alone, untinted.
- **Two columns** from 1024px, three fifths and two fifths: the left holds "Health over the placement", "What moved the scores" and "Calls"; the right holds "Open flags", "Open issues", "Actions" and "Other placements". Narrower, they stack with the right column first.
- **Section cards**: flat (no shadow), a 16px title with the count in a small mono tag. The open flags card takes a red edge while it holds a flag; a critical flag and an overdue action are tinted red at 5%.
- **Evidence**: each quote in its own card, with polarity, dimension and indicator first, then severity, confidence, speaker and, for a contributor, its weight and value (the configuration's value for the signal's polarity and severity), and a link to the moment in the call.
- **Calls**: the table runs to the card's edges with the muted header row; length, signals and actions in mono.
- The screen's subtitles ("Immediate attention", "Top signals by impact", "All recorded sessions", "Reported blockers"), its coloured call-kind pills and its coloured issue dots were left out: RAG colours mean health only, and issues carry no level.

## Motion
- The `motion` library (pinned at 13.4.6) is used in client components only, through `motion/react`.
- `MotionProvider` (`frontend/src/components/providers/MotionProvider.tsx`) sets `reducedMotion="user"`: with the reader's "reduce motion" setting on, transforms and layout animations are skipped.
- The CSS chart entrance (`.chart-animate`) is switched off under `prefers-reduced-motion: reduce`.

## Copy
Every claim on screen is ours and true. Generated designs invented compliance badges (SOC 2, ISO 27001), "encrypted end-to-end", client email ingestion, automatic notifications and "playbooks", version numbers and counts; none of these appear in the app. Sample data on the sign-in page is plainly marked as sample data.
