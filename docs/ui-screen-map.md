# MarketPilot AI — UI Screen Map

Thirteen routes (`/paper` added in Phase 7; `/ai-analyst` implemented for real in Phase 8, see below — it existed as a placeholder route before then). Desktop is the primary experience (see [ui-design-system.md](ui-design-system.md) §1); mobile intelligently re-prioritizes rather than shrinking the desktop layout — each screen below states what that means concretely, not "responsive."

## `/dashboard` — Command Center (rebuilt in Phase 9, see [command-center.md](command-center.md))

- **Primary user goal**: answer, in one glance — what is the market doing, what signals exist, what does the AI Analyst think, what does the Risk Engine say, what is the paper portfolio doing, what happened recently, and is the system healthy.
- **Important information**: system health strip (API/database/redis/market data/AI provider); Market Overview (selected symbol's price, interval, latest timestamp, regime, trend/momentum/volume/volatility state) with the price chart and the Market State instrument alongside it; a watchlist strip; the AI Analyst summary (thesis/action/uncertainty, the deterministic signal it was based on, an explicit disagreement banner when they differ — see [ai-analyst.md](ai-analyst.md) §18); Risk Overview (equity, exposure, drawdown, daily P/L, concurrent positions, active policy/version); Paper Portfolio (equity, cash, market value, unrealized/realized P/L, open positions, clearly labeled PAPER TRADING); Active Signals (direction, strength, status — CANDIDATE/RISK_APPROVED/RISK_REJECTED, always visually distinguished); Recent Activity (a real, backend-derived chronological feed — never fabricated rows, see docs/command-center.md §9 on the fake-data `AlertPreview` this replaced).
- **Primary actions**: change the selected symbol/interval (drives Market Overview + chart + Market State together); follow a Recent Activity event or an "Open ... Center" link through to its owning page for full detail.
- **Secondary actions**: none destructive on this screen — the Command Center is a read/navigate surface; risk review, AI analysis, and paper execution actions live on `/signals` and `/ai-analyst` (which share the same `SignalCenter`/`SignalCard`).
- **Desktop layout**: hero row (Market Overview + chart, paired with the Market State instrument) visually dominates; a watchlist strip below it; a secondary three-column row (AI Analyst / Risk / Paper Portfolio) at equal, subordinate weight; a tertiary row (Active Signals, wide; Recent Activity, narrower).
- **Mobile behavior**: every row collapses to a single column in the same top-to-bottom priority order already established above (hero first); no section is hidden behind a "more" affordance — Step "Responsive design" asks for an intentional single-column reflow, not a data-hiding one, and nothing here is heavy enough to warrant hiding by default.
- **Refresh**: polls `GET /command-center` (+ the chart's own indicator series) every 30 seconds, plus immediately on symbol/interval change — see docs/command-center.md §7 for why polling, not a WebSocket, at this scale.

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

## `/ai-analyst` — AI Analyst Center (implemented in Phase 8, see [ai-analyst.md](ai-analyst.md) §18)

> Deviation from the Phase 1 sketch: rather than a bespoke DATA → ANALYSIS → SIGNAL → RISK → ACTION accordion, Phase 8 reused the Signal Center's own symbol-evaluate panel (`SignalCenter.tsx`, embedded directly, not duplicated) so the AI's analysis, the deterministic signal, the risk decision, and the paper trade status are always the same live view — never a separately-fetched, potentially-inconsistent copy — plus a "Recent AI Analyses" history list across symbols below it.

- **Primary user goal**: understand, for one specific asset, what the AI sees and why, alongside — not instead of — the deterministic signal, risk decision, and paper trade status that actually govern the platform's behavior.
- **Important information**: market overview, AI thesis, supporting/contradicting evidence, risks, invalidating conditions, AI suggested action, qualitative uncertainty (never a numeric confidence), the deterministic signal, the risk decision, paper trade status, and — when the AI's suggestion differs from the deterministic signal — an explicit, never-hidden "Analysis disagreement" status.
- **Primary actions**: switch analyzed asset (symbol selector); run AI analysis; proceed through risk review and paper execution from the same card (unchanged from the Signal Center, Phase 6/7).
- **Secondary actions**: browse recent AI analyses across symbols.
- **Desktop layout**: single-column — symbol selector and signal card (with the AI Analyst section between the deterministic signal and the risk/paper-trade lifecycle) on top, recent-analyses history table below.
- **Mobile behavior**: same vertical order; the evidence lists (supporting/contradicting evidence, risks, invalidating conditions) remain always-visible rather than collapsing, since Step 21's disagreement-visibility requirement means nothing about the AI's reasoning should be hidden behind an extra tap.
- **Unavailable state**: when `AI_PROVIDER_API_KEY` isn't configured, an explicit "AI Analyst unavailable — configure the Claude provider to enable analysis." message replaces the "Run AI Analysis" action — never a blank or broken-looking section.

## `/paper` — Paper Trading Center (Phase 7, not in the original sketch)

> Phase 7 consolidated what the sketch spread across `/portfolio`, `/positions`, and `/trades` into one screen — see docs/paper-trading.md §20. Each of those three routes still exists (below) but now just points here for the functionality that's actually real, reserving its own space for the analytics/history depth the sketch originally imagined.

- **Primary user goal**: see the real, current state of the one simulated paper-trading account, and act on it.
- **Important information**: account (starting equity, cash, equity, total/daily P/L, drawdown), open positions (symbol, quantity, average entry, current price, market value, unrealized P/L), recent simulated orders (side, quantity, requested/fill price, status), recent simulated fills (fee, timestamp).
- **Primary actions**: close an open position (`POST /paper/positions/{symbol}/close`).
- **Secondary actions**: none yet — order submission is signal-driven only (`POST /paper/execute/{signal_id}`, initiated from the Signal Center after risk approval, not from this screen).
- **Desktop layout**: account stat row at top, positions table, orders table, recent fills table below.
- **Mobile behavior**: account stats become a horizontally-scrollable strip; tables scroll horizontally within their own container rather than the page.

## `/portfolio`

> **Phase 7 status**: basic equity/cash/P&L/drawdown are real — see `/paper` above. This screen is reserved for what `/paper` doesn't cover: win rate, profit factor, and a longer equity-curve history — arrives with Phase 10 ("Portfolio analytics").

- **Primary user goal**: understand overall paper-trading performance.
- **Important information**: value, cash, P/L (unrealized/realized/daily/total), drawdown, win rate, profit factor, equity curve.
- **Primary actions**: change performance time range; drill into a specific period.
- **Secondary actions**: export/share performance (future; not in MVP scope).
- **Desktop layout**: summary stat row, `PerformanceChart` (equity curve) as the visual centerpiece, secondary stats below.
- **Mobile behavior**: stat row becomes a horizontally-scrollable strip; chart stays full-width and is the first thing shown.

## `/positions`

> **Phase 7 status**: open positions are real — see `/paper` above. This screen is reserved for closed-position history (`/paper` only lists open positions today) — arrives with a later phase.

- **Primary user goal**: review current and historical paper positions in detail.
- **Important information**: symbol, side, quantity, entry/current price, unrealized/realized P/L, risk status.
- **Primary actions**: filter open/closed; open a position's trade history.
- **Secondary actions**: submit a closing order (routes to `/trades` submission, risk-gated).
- **Desktop layout**: `PositionsTable`, filterable, sortable by P/L.
- **Mobile behavior**: card-per-position; P/L is the most prominent number per card (larger than symbol), since that's what a mobile glance is usually for.

## `/trades`

> **Phase 7 status**: simulated order/fill history is real — see `/paper` above. Order submission there is signal-driven only; this screen's free-form "submit a new order for any asset/side/quantity" form is reserved for a later phase, since Phase 7 scoped execution to signals the Risk Engine already approved (docs/paper-trading.md §18's deviation note).

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
