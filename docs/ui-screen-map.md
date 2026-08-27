# MarketPilot AI — UI Screen Map

Twelve routes. Desktop is the primary experience (see [ui-design-system.md](ui-design-system.md) §1); mobile intelligently re-prioritizes rather than shrinking the desktop layout — each screen below states what that means concretely, not "responsive."

## `/dashboard` — Command Center

- **Primary user goal**: answer "what is the state of the market and my portfolio, right now?" in one glance.
- **Important information**: global market status, AI market assessment (signature instrument), watchlist, active signals, portfolio performance, risk exposure, open positions, recent alerts, activity timeline.
- **Primary actions**: open an asset's AI Analyst view; open a signal's full reasoning.
- **Secondary actions**: add/remove a watchlist symbol inline; mark an alert read.
- **Desktop layout**: three-column hero row (AI assessment / portfolio / risk), then watchlist+signals row, then positions+alerts row, then a full-width activity timeline — see the [Command Center mockup](../design/command-center/).
- **Mobile behavior**: reorders to a single column, prioritized: AI assessment → portfolio summary (collapsed to headline numbers) → active signals → watchlist → positions → alerts. The activity timeline and detailed risk bars move to a "more" expansion rather than appearing by default — they're monitoring detail, not the mobile user's first need.

## `/markets`

- **Primary user goal**: browse and research assets beyond the watchlist.
- **Important information**: asset list by class (equity/ETF/crypto/forex), price, change %, price chart on selection.
- **Primary actions**: search/filter assets; select an asset to view its chart and jump to AI Analyst.
- **Secondary actions**: add an asset to a watchlist from this screen.
- **Desktop layout**: filterable list/table on the left, selected asset's `PriceChart` and key stats on the right.
- **Mobile behavior**: list-first; selecting an asset pushes to a full-screen detail view rather than a split pane.

## `/watchlist`

- **Primary user goal**: manage and monitor the assets the user has chosen to track.
- **Important information**: price, change %, current signal, per watchlist.
- **Primary actions**: add/remove symbols; reorder; create additional watchlists.
- **Secondary actions**: jump to `/markets` detail or `/ai-analyst` for a symbol.
- **Desktop layout**: table (`Watchlist` component), watchlist selector as tabs if the user has more than one.
- **Mobile behavior**: card-per-symbol list instead of a dense table — the table's column count doesn't survive a narrow viewport with the numbers still legible.

## `/signals`

- **Primary user goal**: see everything the deterministic signal engine currently considers active, across all assets (not just the watchlist).
- **Important information**: direction, strength, asset, generation time.
- **Primary actions**: filter by direction/asset class/strength; open a signal's [premium signal card](../design/command-center/SignalCard.dc.html) for full reasoning.
- **Secondary actions**: jump to the asset's AI Analyst view.
- **Desktop layout**: filterable table/list, expandable rows using the signal card component.
- **Mobile behavior**: filters collapse into a single sheet/drawer; rows are pre-collapsed cards, tap to expand (matches the signal card's own collapsed/expanded design).

## `/ai-analyst`

- **Primary user goal**: understand, for one specific asset, what the AI sees and why — with DATA/ANALYSIS/SIGNAL/RISK/ACTION kept visually distinct (see [ai-architecture.md](ai-architecture.md), [ui-design-system.md](ui-design-system.md)).
- **Important information**: raw indicator data, narrative analysis, signal recap with supporting/contradicting indicators, risk level and price zones, thesis invalidation.
- **Primary actions**: switch analyzed asset; proceed to `/trades` to submit a paper order (still gated by the risk engine).
- **Secondary actions**: add asset to watchlist; view the signal's full history.
- **Desktop layout**: single-column, ordered top-to-bottom exactly DATA → ANALYSIS → SIGNAL → RISK → ACTION (mirrors the mockup at [`AIAnalyst.dc.html`](../design/command-center/AIAnalyst.dc.html)) — the vertical order itself teaches the platform's DATA → interpretation → decision model.
- **Mobile behavior**: same section order, each section becomes a collapsible accordion so the page doesn't require excessive scrolling to reach ACTION; DATA and ANALYSIS collapse by default, SIGNAL/RISK/ACTION stay expanded since they're what most users came for.

## `/portfolio`

- **Primary user goal**: understand overall paper-trading performance.
- **Important information**: value, cash, P/L (unrealized/realized/daily/total), drawdown, win rate, profit factor, equity curve.
- **Primary actions**: change performance time range; drill into a specific period.
- **Secondary actions**: export/share performance (future; not in MVP scope).
- **Desktop layout**: summary stat row, `PerformanceChart` (equity curve) as the visual centerpiece, secondary stats below.
- **Mobile behavior**: stat row becomes a horizontally-scrollable strip; chart stays full-width and is the first thing shown.

## `/positions`

- **Primary user goal**: review current and historical paper positions in detail.
- **Important information**: symbol, side, quantity, entry/current price, unrealized/realized P/L, risk status.
- **Primary actions**: filter open/closed; open a position's trade history.
- **Secondary actions**: submit a closing order (routes to `/trades` submission, risk-gated).
- **Desktop layout**: `PositionsTable`, filterable, sortable by P/L.
- **Mobile behavior**: card-per-position; P/L is the most prominent number per card (larger than symbol), since that's what a mobile glance is usually for.

## `/trades`

- **Primary user goal**: see trade history, and submit a new paper order.
- **Important information**: fill price, quantity, fees, P/L per trade, timestamp.
- **Primary actions**: submit a new order (asset, side, quantity) — always routes through the risk engine; result (approved/rejected) shown immediately with the reason.
- **Secondary actions**: filter trade history by asset/date.
- **Desktop layout**: order submission panel + risk-decision feedback at top, trade history table below.
- **Mobile behavior**: order submission becomes a full-screen form/sheet; history stays a simple list below it.

## `/risk`

> **Phase 6 status**: implemented as the "Risk Center" (`RiskCenter.tsx`) — live exposure/drawdown/daily-P&L/concurrent-position panel, the active policy's limits, and a recent-decisions feed, all real (docs/risk-engine.md §12). The editable rule form below is **not built yet**: `PUT /risk/rules` exists and is fully validated server-side, but this phase scoped the UI to *showing* the policy, not editing it in-browser — editing is API-only for now. Also added beyond this sketch: a "Recent Decisions" feed (approve/reject history with reasons), since Step 21 of the Phase 6 plan asked for it explicitly.

- **Primary user goal**: understand current risk exposure and the deterministic rules that govern it.
- **Important information**: live exposure/daily-loss/drawdown/concurrent-position bars vs. configured limits ([api.md](api.md) `GET /risk`); the configured rule values themselves ([api.md](api.md) `GET/PUT /risk/rules`); recent approve/reject decisions.
- **Primary actions**: none yet in-browser (rules are read-only in this phase's UI) — see status note above.
- **Secondary actions**: view which currently-open positions contribute most to exposure (blocked on Phase 7's position tracking).
- **Desktop layout**: live exposure summary + policy limits side by side, recent decisions list below.
- **Mobile behavior**: same sections stacked.

## `/alerts`

- **Primary user goal**: review everything the system has flagged — signals, risk thresholds, profit-protection events.
- **Important information**: type, severity, message, timestamp, read/unread ([profit-protection.md](profit-protection.md)).
- **Primary actions**: mark read; filter by severity/type.
- **Secondary actions**: jump to the related entity (asset, position) from an alert.
- **Desktop layout**: `AlertsTimeline`, filterable, unread visually distinguished (not color-only — a dot/weight change per [ui-design-system.md](ui-design-system.md) §8).
- **Mobile behavior**: same list; this screen already degrades well to a single column, so mobile layout is close to identical to desktop, just full-width.

## `/backtests`

- **Primary user goal**: evaluate a strategy against historical data before trusting it live in paper trading.
- **Important information**: strategy, date range, status, summary results (return, win rate, drawdown, trade count).
- **Primary actions**: configure and run a new backtest; view a completed backtest's detail.
- **Secondary actions**: compare two backtests (future; not MVP scope).
- **Desktop layout**: run-configuration panel + list of past runs with status; completed runs expand into a results summary (reusing `PerformanceChart` styling for the equity curve).
- **Mobile behavior**: configuration becomes a full-screen form; results list is a simple card list; a running backtest shows a status card rather than the user waiting on the screen (results are available whenever they return).

## `/settings`

- **Primary user goal**: manage account, watchlists administration, and platform preferences.
- **Important information**: user profile, theme (dark/light), notification preferences.
- **Primary actions**: update profile; switch theme.
- **Secondary actions**: manage API/integration settings as they're added post-MVP.
- **Desktop layout**: simple form sections, no dense data — this screen is deliberately the least "instrument panel" screen in the product.
- **Mobile behavior**: identical structure, single column by default on desktop too.
