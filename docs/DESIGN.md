# Design System

> **Status**: Sprint 3 Phase 1 (2026-10-12): the Twilight direction, its light and twilight-dark colours, fonts, logo and motion settings are built. The shell, the sign-in showcase and the redesigned pages follow phase by phase; each section below says what is built.

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
The app opens in the light theme (`defaultTheme="light"`); twilight dark and the system setting are in the theme menu. Every page works in both.

## Motion
- The `motion` library (pinned at 13.4.6) is used in client components only, through `motion/react`.
- `MotionProvider` (`frontend/src/components/providers/MotionProvider.tsx`) sets `reducedMotion="user"`: with the reader's "reduce motion" setting on, transforms and layout animations are skipped.
- The CSS chart entrance (`.chart-animate`) is switched off under `prefers-reduced-motion: reduce`.

## Copy
Every claim on screen is ours and true. Generated designs invented compliance badges (SOC 2, ISO 27001), "encrypted end-to-end", client email ingestion, automatic notifications and "playbooks", version numbers and counts; none of these appear in the app. Sample data on the sign-in page is plainly marked as sample data.
