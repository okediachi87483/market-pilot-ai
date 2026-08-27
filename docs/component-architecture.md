# MarketPilot AI — Component Architecture

Companion to [architecture.md](architecture.md). Defines the frontend component tree and backend service modules, and how they communicate.

## 1. Frontend components

All components are React (Next.js App Router), TypeScript strict. Presentational components take typed props derived from the API's Pydantic response schemas (kept in sync via generated types — see [api.md](api.md) §"Typed client"). No component fetches data it doesn't render; data fetching lives in route-level server components or hooks, not deep in the tree.

| Component | Purpose | Reads from | Used on |
|---|---|---|---|
| `CommandCenter` | Top-level composition of the primary dashboard layout — as built (Phase 9), a grid of the sub-sections below off **one** aggregated snapshot, not N independent per-panel fetches. | `GET /command-center` (docs/command-center.md), `GET /analysis/{symbol}/indicators` (chart only) | `/dashboard` |
| `MarketStateVisualization` | The signature Market State instrument (see [ui-design-system.md](ui-design-system.md) §7). Renders the detected regime (BULLISH/BEARISH/SIDEWAYS/HIGH_VOLATILITY/LOW_VOLATILITY/INSUFFICIENT_DATA) as a gauge, never a bare badge, and never a numeric AI confidence — the needle position is derived from the same deterministic `trend_alignment_score`/`trend_direction` the technical-analysis engine already computed. Accepts pre-fetched `data` (Phase 9) to avoid a duplicate request when embedded in `CommandCenter`; self-fetches via `GET /analysis/{symbol}` otherwise. | `GET /analysis/{symbol}` (self-fetch mode) or injected `data` | `/dashboard` |
| `SignalCenter`/`SignalCard` | Full signal lifecycle for one symbol — signal, AI analysis, risk decision, paper trade status — reused directly (not duplicated) by both `/signals` and `/ai-analyst`. | `POST /signals/evaluate/{symbol}`, `POST /risk/evaluate/{signal_id}`, `POST /ai/analyze/{signal_id}`, `POST /paper/execute/{signal_id}` | `/signals`, `/ai-analyst` |
| `PriceChart` | Price + EMA9/21 + SMA20 + Bollinger Bands + volume for one asset — all backend-calculated, the frontend only scales coordinates. | `GET /analysis/{symbol}/indicators` | `/markets`, `/dashboard` (Command Center hero) |

The Command Center's own internal sections (Market Overview, Watchlist strip, AI Analyst summary, Risk Overview, Paper Portfolio, Active Signals, Recent Activity, System Health) are private to `CommandCenter.tsx` (docs/command-center.md) rather than independently reusable components — each is tightly coupled to the one aggregated snapshot's shape and has no reason to be instantiated on its own, the same reasoning `SignalCard`'s internal `AIAnalystSection` helper already established in Phase 8. `AlertsTimeline`/`PerformanceChart`/a real `Watchlist` backed by `GET /watchlists` remain not-yet-built (their owning phases — alerts/portfolio-analytics — haven't landed).

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
