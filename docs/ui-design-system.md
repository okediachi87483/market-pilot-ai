# MarketPilot AI — UI Design System

Reference implementation (mockups, not production code): the [MarketPilot Command Center design canvas](../design/command-center/). This document is the written specification those mockups implement — the source of truth for values; the canvas is the source of truth for how they compose visually. Read together; kept in sync by hand until Phase 2 lifts these tokens into `apps/web`'s Tailwind config.

## 1. Direction

MarketPilot must not read as a generic SaaS admin panel. The identity is: **precision, intelligence, trust, speed, control.** Dark-mode-first, institutional, calm — closer to instrument-panel design than dashboard-template design. Bloomberg/Apple/Stripe/Linear/Palantir are quality references, never visual sources — nothing here recreates their specific UI patterns.

Explicitly avoided, and checked against on every screen: generic Bootstrap/admin-template layouts, generic SaaS card grids, excessive rounded corners, purple AI gradients, neon/cyberpunk styling, glassmorphism, overloaded charts, gratuitous animation, and status communicated by color alone.

## 2. Typography

**IBM Plex Sans** (UI text) + **IBM Plex Mono** (all numerical/financial data — prices, percentages, quantities, timestamps). The pairing is deliberate: distinguishing "this is a number you should trust as precise" from "this is UI chrome" by typeface, not just size, reinforces the instrument-panel feel and avoids the generic-SaaS default of Inter/Roboto/Arial everywhere.

| Token | Size / line-height / weight | Use |
|---|---|---|
| `display-xl` | 44px / 1.1 / 600 | Hero numbers (portfolio value) |
| `display-lg` | 32px / 1.15 / 600 | Page/section titles |
| `heading-lg` | 22px / 1.3 / 600 | Panel titles |
| `heading-md` | 17px / 1.35 / 600 | Card titles |
| `body` | 14px / 1.5 / 400 | Primary reading text |
| `body-sm` | 13px / 1.5 / 400 | Secondary text |
| `label` | 11px / 1.3 / 600, uppercase, 0.08em tracking | Eyebrows, table headers |
| `mono-data-lg` | 20px / 1.3 / 500, IBM Plex Mono | Prominent price/metric values |
| `mono-data-sm` | 12px / 1.3 / 500, IBM Plex Mono | Table cells, timestamps |

## 3. Color

Dark is the default and primary experience; light is a supported alternate, not an afterthought, defined with the same hue relationships. All values in OKLCH for perceptually-consistent lightness/chroma steps.

### Dark (default)

| Token | Value | Use |
|---|---|---|
| `bg-0` | `oklch(14% 0.014 250)` | Page base |
| `bg-1` | `oklch(17% 0.016 250)` | Surface / card |
| `bg-2` | `oklch(21% 0.018 250)` | Raised surface |
| `bg-3` | `oklch(25% 0.02 250)` | Overlay / modal |
| `border-subtle` | `oklch(28% 0.02 250)` | Default hairline |
| `border-default` | `oklch(34% 0.022 250)` | Emphasized border |
| `text-primary` | `oklch(96% 0.006 250)` | Primary text |
| `text-secondary` | `oklch(72% 0.012 250)` | Secondary text |
| `text-tertiary` | `oklch(52% 0.014 250)` | Tertiary / labels |
| `accent-teal` | `oklch(72% 0.11 200)` | Interactive / brand accent |
| `accent-amber` | `oklch(75% 0.14 70)` | AI emphasis, risk/warning |
| `positive` | `oklch(70% 0.15 145)` | Bullish / gains |
| `negative` | `oklch(66% 0.19 25)` | Bearish / losses |
| `neutral-signal` | `oklch(62% 0.01 250)` | Neutral state |

### Light (alternate)

| Token | Value |
|---|---|
| `bg-0` | `oklch(98% 0.004 250)` |
| `bg-1` | `oklch(100% 0 0)` |
| `text-primary` | `oklch(18% 0.012 250)` |
| `text-secondary` | `oklch(38% 0.014 250)` |
| `accent-teal` | `oklch(48% 0.11 200)` |
| `accent-amber` | `oklch(52% 0.14 70)` |
| `positive` | `oklch(46% 0.15 145)` |
| `negative` | `oklch(50% 0.19 25)` |

Deliberately no purple/violet accent anywhere in the palette — see §1.

## 4. Spacing, radius, elevation

- **Spacing scale (px)**: 4, 8, 12, 16, 20, 24, 32, 40, 56, 72.
- **Radius**: `sm` 4px (chips, inputs) · `md` 6px (cards, buttons) · `lg` 10px (panels). Deliberately restrained — no large rounded rectangles.
- **Borders**: 1px hairline is the default separator, not shadow. `border-subtle` for internal structure, `border-default` for emphasis/focus/selection.
- **Elevation**: expressed as surface lightness steps (`bg-0` → `bg-3`), not drop shadows. The one shadow in the system (`0 8px 24px oklch(0% 0 0 / 0.35)`) is reserved for true overlays (modals, popovers) — cards never float on shadow alone.

## 5. Status & signal language

**A state is always glyph + color + text label together — never color alone**, both for accessibility (see §8) and because a bare colored badge is exactly the generic pattern this product avoids. Six states, each with a distinct stroke-based glyph (16-24px grid, consistent weight, `currentColor` so it recolors with state):

| State | Glyph | Color |
|---|---|---|
| BULLISH | Upward triangle | `positive` |
| BEARISH | Downward triangle | `negative` |
| NEUTRAL | Horizontal dash | `neutral-signal` |
| HIGH RISK | Diamond outline + exclamation | `accent-amber` |
| MARKET CLOSED | Clock ring | `text-tertiary` |
| VOLATILITY EVENT | Zigzag/pulse | `accent-amber`, with a pulsing ring (see §7) |

The same glyph set is reused for row-level signal tags (LONG BIAS, SHORT BIAS, NEUTRAL, HIGH RISK) in tables — one status vocabulary everywhere it appears, not a bespoke treatment per screen.

## 6. Components

- **Buttons**: primary (filled `accent-teal`, dark text), secondary (bordered, `bg-2`), ghost (text only), destructive (bordered `negative`), disabled (`bg-1`, `text-tertiary`, no pointer). No gradients.
- **Inputs**: `bg-1` fill, `border-default` outline, `accent-teal` focus ring (3px, 18% opacity), `negative` border on error. Select/dropdown shares the same shell with a trailing chevron glyph.
- **Tables**: hairline row separators, no zebra striping, numeric columns right-aligned in `mono-data-sm`, header row in `label` style.
- **Cards**: `bg-1` on `bg-0`, `border-subtle`, `radius-md`, `label`-style eyebrow at the top identifying the card's category (mirrors the DATA/ANALYSIS/SIGNAL/RISK/ACTION separation used on the AI Analyst screen — see [ui-screen-map.md](ui-screen-map.md)).
- **Alerts**: severity communicated by the same glyph+color+label pattern as §5 (info/warning/critical), never a colored strip alone.
- **Navigation**: slim top bar, text tabs with a 2px `accent-teal` underline for the active route — no icon-heavy sidebar; the product is desktop-primary and data-dense, so navigation stays out of the way of content.
- **Modals**: `bg-3`, `radius-lg`, the one drop-shadow in the system, reserved for genuinely blocking interactions (confirming a destructive action, editing risk rules).
- **Tooltips**: `bg-3`, `border-default`, `body-sm`, used for exact values behind rounded/abbreviated display numbers (e.g. hovering a chart point, hovering the sentiment instrument's confidence ring).
- **Empty / loading / error states**: every data panel defines its own three states rather than a generic spinner — empty states explain *why* (e.g. "No signals match your filters" vs. "No watchlist items yet — add a symbol to get started"); loading states are skeleton shapes matching the eventual content's layout, not a centered spinner that causes layout shift; error states name what failed and, where applicable, whether it's retryable (a market-data provider outage reads differently from a validation error).

## 7. Signature UI: the Market State Visualization

This is MarketPilot's one deliberately distinctive UI element — the component users should recognize the product by. Implemented as `SentimentInstrument` ([component-architecture.md](component-architecture.md)), rendered in the canvas mockups.

**Form**: a semicircular instrument gauge (not a dial that spins fully, not a bar) — a 180° arc from bearish (left) through neutral (top) to bullish (right), divided into three tinted zones, with a needle pointing to the current sentiment score (-100 to +100). Below the arc: the state label with its glyph (§5), a confidence readout, and an "as of" timestamp. The geometry deliberately reads as an instrument — closer to an aircraft attitude indicator than a marketing gauge — reinforcing "you are operating an intelligent monitoring system," not "you are looking at a chart."

**Reuse, not a one-off**: the same component renders at three sizes/contexts — hero (Command Center centerpiece), compact (the six-state reference strip, and the per-asset badge on the AI Analyst screen), and inline within table rows via the shared glyph set. One visual language, several scales — never a bespoke "sentiment widget" redrawn per screen.

**Interaction and behavior**:
- **Idle**: static — arc, needle, label, confidence. No motion for a steady state; MarketPilot's stance on animation is that it should mean something (see §1).
- **State transition**: when the underlying score changes (new signal, new AI analysis), the needle animates to its new position over ~400ms with an eased transition — the one place continuous motion is used deliberately, because a snapping needle reads as a glitch and a sentiment shift is genuinely notable.
- **Volatility event**: a soft pulsing ring animates around the instrument's center for as long as `VOLATILITY_EVENT` is the active state — motion as a properly-earned alert signal, not decoration used elsewhere.
- **Market closed**: the needle and arc dim to ~25% opacity; the label and clock glyph take over as the primary read, communicating "this number is not currently live" without hiding it entirely.
- **Hover / focus**: reveals an exact numeric readout (score, confidence, as-of timestamp) in a tooltip — the gauge shows the read at a glance, the tooltip gives the precise data underneath, matching the platform-wide DATA-vs-interpretation separation.
- **Click** (hero instance only): navigates to the corresponding `/ai-analyst` detail view for full reasoning — the instrument is a summary, not a dead end.
- **Reduced motion**: honors `prefers-reduced-motion` — the needle transition and volatility pulse are both disabled in favor of an instant state change; nothing about the component's meaning depends on the animation being visible.

## 8. Accessibility

- Status is never color-only (§5, §7). Every colored state has a text label and, where feasible, a distinct glyph shape (not just a recolored dot).
- Keyboard navigation and visible focus states (2px `accent-teal` outline, never `outline: none` without a replacement) on every interactive element.
- Contrast: body text against `bg-0`/`bg-1` targets WCAG AA at minimum in both themes; `text-tertiary` is reserved for genuinely secondary/label content, never for anything a user must read to understand system state.
- Semantic HTML and ARIA where native semantics fall short (e.g. the sentiment instrument exposes its state via `aria-label`/`role="img"` with a text description, and state transitions are announced via a polite `aria-live` region — a screen reader user gets "AI market assessment: bullish, confidence 81 percent" without needing to parse an SVG).
- `prefers-reduced-motion` is honored everywhere motion is used (§7 and elsewhere — signal-appearance, panel-expansion, and alert-notification animation are all disabled or reduced to instant-state-changes under the media query).
