# MarketPilot AI — Component Architecture

Companion to [architecture.md](architecture.md). Defines the frontend component tree and backend service modules, and how they communicate.

## 1. Frontend components

All components are React (Next.js App Router), TypeScript strict. Presentational components take typed props derived from the API's Pydantic response schemas (kept in sync via generated types — see [api.md](api.md) §"Typed client"). No component fetches data it doesn't render; data fetching lives in route-level server components or hooks, not deep in the tree.

| Component | Purpose | Reads from | Used on |
|---|---|---|---|
| `CommandCenter` | Top-level composition of the primary dashboard layout (grid of the components below). | — (layout only) | `/dashboard` |
| `MarketOverview` | Global market status strip: session state (open/closed), index snapshot, timestamp. | `GET /market/{symbol}` (indices) | `/dashboard`, `/markets` |
| `MarketStateVisualization` | The signature AI sentiment instrument (see [ui-design-system.md](ui-design-system.md) §"Signature UI concept"). Renders score, confidence, and state (BULLISH/BEARISH/NEUTRAL/HIGH_RISK/MARKET_CLOSED/VOLATILITY_EVENT) as a gauge, never a bare badge. | `GET /analysis/{symbol}` (portfolio-level aggregate for the dashboard instance; per-asset instance on `/ai-analyst`) | `/dashboard`, `/ai-analyst` |
| `Watchlist` | User's tracked assets with live(ish) price, change %, and current signal. | `GET /watchlists`, `GET /market/{symbol}` per row | `/dashboard`, `/watchlist` |
| `SignalPanel` | List of active signals; each row expandable into the full [premium signal card](ui-design-system.md). | `GET /signals` | `/dashboard`, `/signals` |
| `AIInsightPanel` | DATA / ANALYSIS / SIGNAL / RISK / ACTION breakdown for one asset. | `GET /analysis/{symbol}` | `/ai-analyst` |
| `PortfolioSummary` | Value, cash, daily/total P/L, sparkline. | `GET /portfolio` | `/dashboard`, `/portfolio` |
| `RiskPanel` | Exposure, daily loss, drawdown, concurrent positions vs. configured limits. | `GET /risk` | `/dashboard`, `/risk` |
| `PositionsTable` | Open (and, on `/positions`, closed) paper positions with unrealized/realized P/L. | `GET /positions` | `/dashboard`, `/positions` |
| `AlertsTimeline` | Recent alerts feed, including profit-protection alerts. | `GET /alerts` | `/dashboard`, `/alerts` |
| `MarketActivityTimeline` | Chronological log of signals generated, AI analyses updated, orders filled, alerts triggered. | Composed client-side from `GET /signals`, `GET /trades`, `GET /alerts` (recent, time-windowed) | `/dashboard` |
| `PriceChart` | OHLCV chart for one asset (lightweight-charts). | `GET /market/{symbol}/history` | `/markets`, `/watchlist` (detail), `/ai-analyst` |
| `PerformanceChart` | Portfolio equity curve over time. | `GET /portfolio/performance` | `/portfolio` |

Shared primitives (buttons, inputs, tables, cards, tags, tooltips, modals, empty/loading/error states) live in `apps/web/components/ui/` per [ui-design-system.md](ui-design-system.md) and are the only building blocks the components above are allowed to use for chrome — no ad hoc styling per screen.

## 2. Backend service modules

One-to-one with the packages in [architecture.md](architecture.md) §3. Each exposes a `service.py` as its only public surface; `models.py` (SQLAlchemy) and internal helpers are not imported by anything outside the package.

| Service | Public interface (representative) | Called by |
|---|---|---|
| `MarketDataService` | `get_latest(asset_id)`, `get_history(asset_id, range)`, `ingest_cycle()` | scheduler, `apps/api` routers (`/market/*`), `IndicatorService` |
| `IndicatorService` | `compute(asset_id, timeframe)`, `get_latest(asset_id)` | scheduler, `SignalService` |
| `SignalService` | `evaluate(asset_id)`, `list_active(filters)`, `get(signal_id)` | scheduler, `apps/api` routers (`/signals/*`), `AIAnalysisService` |
| `AIAnalysisService` | `analyze(signal_id)`, `get_latest(asset_id)` | scheduler, `apps/api` routers (`/analysis/*`), `RiskService` |
| `RiskService` | `evaluate(proposed_order)`, `get_rules(portfolio_id)`, `update_rules(portfolio_id, rules)` | scheduler, `apps/api` routers (`/risk/*`), `PaperTradingService` |
| `PaperTradingService` | `submit_order(order)`, `list_trades(filters)` | scheduler (auto-approved flow), `apps/api` routers (`/trades`, user-initiated) |
| `PortfolioService` | `get_summary(portfolio_id)`, `get_performance(portfolio_id, range)` | `apps/api` routers (`/portfolio/*`), `RiskService`, `AlertService` |
| `AlertService` | `evaluate_cycle(portfolio_id)`, `list(filters)` | scheduler, `apps/api` routers (`/alerts`) |
| `AuditService` | `record(actor, action, entity, before, after, metadata)` | every other service, at every state-changing write |

## 3. Communication rules

- **Frontend → backend**: REST only, over the API defined in [api.md](api.md). No direct DB access, no GraphQL, no backend-for-frontend layer in the MVP — one API is simple enough at this scale and avoids a second contract to keep in sync.
- **Backend package → package**: direct Python function calls through `service.py`, inside one process, inside one DB transaction where the operation is logically atomic (e.g. "approve order and create it" commits together). No message queue in the MVP — see [architecture.md](architecture.md) §9 for when that changes.
- **Near-real-time UI updates**: Redis pub/sub channels (`channel:signals`, `channel:alerts`, `channel:prices`) that `apps/api` relays to connected clients over Server-Sent Events (SSE) or WebSocket (implementation choice deferred to Phase 2; SSE is the lower-complexity default for one-way server→client push). The frontend must work correctly on polling alone if the push channel is unavailable — push is a latency optimization, not a dependency.
- **Backend package → AI provider**: only `ai-engine` ever calls out to an LLM. No other package holds AI provider credentials or imports an AI SDK.
