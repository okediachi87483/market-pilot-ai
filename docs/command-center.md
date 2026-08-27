# MarketPilot AI — Command Center

Phase 9. The Command Center (`/dashboard`) is the primary operational dashboard — it answers, in one glance: what is the market doing, what signals exist, what does the AI Analyst think, what does the Risk Engine say, what is the paper portfolio doing, what happened recently, and is the system healthy. This phase does not add a new domain — it composes and presents what Phases 3–8 already built.

## 1. Architecture

```
CommandCenter.tsx (apps/web/components/market/CommandCenter.tsx)
        │
        ├─ GET /api/v1/command-center     — one aggregated snapshot (§2)
        │     (system health, market, watchlist, signals, ai_analyses,
        │      risk, portfolio, positions, recent_fills, recent_activity)
        │
        └─ GET /api/v1/analysis/{symbol}/indicators   — the price chart's
              own series, fetched separately (§3)
```

Two requests per load/refresh, not the ~10 the previous dashboard made (one per preview card: market status, market state, watchlist ×3 quotes, signals ×3 evaluations, risk, portfolio, AI status + AI analyses + signal + risk evaluation, alerts). The old per-panel preview components (`RiskPreview`, `PortfolioPreview`, `SignalPreview`, `WatchlistPreview`, `AIAnalystPreview`, `MarketStatusPreview`) and the fabricated-data `AlertPreview` are removed — `dashboard/page.tsx` now renders only `CommandCenter`.

## 2. `GET /api/v1/command-center` (Step "API efficiency")

`app/api/v1/command_center.py` — a read-only aggregation, not a new domain. Every field is either a direct call into an existing service's existing public method (`SignalService.list_signals`, `RiskService.get_active_policy`/`get_portfolio_snapshot`, `PaperTradingService.get_portfolio_state`/`list_positions`/`list_fills`, `AIAnalystService.list_analyses`/`get_status`, `TechnicalAnalysisService.get_snapshot`, `MarketDataService.get_quote`) or a small presentation-only composition of those results (merging and sorting into `recent_activity`, §5). No domain logic is duplicated or reimplemented — aggregation strictly lives at this API boundary, per the phase's own instruction.

Query parameters: `symbol` (default `AAPL` — the selected asset for Market Overview + the price chart), `interval` (default `1d`), `watchlist` (comma-separated, default `AAPL,MSFT,NVDA,TSLA`), `activity_limit` (default 15, max 50).

**Failure behavior**: an unknown `symbol` propagates as `404` for the whole response — it's the one section the caller explicitly asked for by name, and every other per-symbol endpoint in this codebase (`GET /analysis/{symbol}`, `GET /market/{symbol}`) behaves the same way. An unknown symbol *inside the watchlist* is silently skipped instead — the watchlist is best-effort by design (§4). Every other section (signals, AI analyses, risk, portfolio) is a plain, already-tested database read through a trusted service; consistent with every other endpoint in this codebase, a genuine failure there (e.g. a real database outage) is a `500`/`503` for the whole response rather than a silently-degraded section, matching `docs/architecture.md` §7's "Database unavailable... API returns 503" precedent. What Step "Error states" actually asks for — an unavailable AI Analyst must not take down market/signals/risk/portfolio — is satisfied because "AI not configured" is not a failure at all: `system_health.ai.available: false` and an empty `ai_analyses: []` are normal, successful parts of one `200` response, handled by the AI Analyst panel's own empty/unavailable state (§6) while every other panel renders normally from the same response.

## 3. Market Overview + price chart

`market` in the snapshot mirrors `GET /analysis/{symbol}` (docs/technical-analysis.md) minus the full per-indicator arrays: symbol, interval, source/is_mock, calculated_at, candle_count, latest price+timestamp, the derived feature labels (trend direction/alignment, RSI/MACD/volume/volatility state), and the detected regime. The price chart itself (`PriceChart.tsx`, price + EMA9/21 + SMA20 + Bollinger Bands + volume, all backend-calculated) is fed by a *separate* call to the existing `GET /analysis/{symbol}/indicators` — deliberately kept out of the aggregated snapshot, since a full point series is a meaningfully larger payload than the rest of the snapshot combined and doesn't need to be re-fetched on every 30s poll tick at the same cadence as everything else (in practice it is refetched on the same cadence today, for one cohesive "refresh" mental model, §7 — but architecturally it's decoupled, so a future change to poll it less frequently doesn't touch the snapshot endpoint at all).

## 4. Watchlist strip

Best-effort, not all-or-nothing: `command_center.py` fetches a quote per requested watchlist symbol and silently drops any that fail (unknown symbol, provider error) rather than failing the whole request — the same principle Step "Error states" asks for, applied to a list instead of independent panels. `change_pct` is derived server-side from the same bar's own open/close (`(close-open)/open*100`), never a separately fabricated number — the identical computation the old `WatchlistPreview.tsx` did client-side, now done once, server-side, for every viewer.

## 5. Recent Activity

A single chronological feed merged from four independently-owned, already-existing read paths — `SignalService.list_signals`, `RiskService.list_evaluations`, `AIAnalystService.list_analyses`, `PaperTradingService.list_fills` — each mapped to one of six fixed event types (`SIGNAL_GENERATED`, `RISK_APPROVED`, `RISK_REJECTED`, `AI_ANALYSIS_COMPLETED`, `PAPER_ORDER_FILLED`, `POSITION_CLOSED` — a fill with a non-null `realized_pnl` is a close, not a fresh open) and sorted by each row's own real timestamp, descending. Nothing here is synthesized — every event corresponds to a real row that already existed for its own owning phase's own reasons; `command_center.py` only merges and sorts. Each event links to its owning page (`/signals`, `/risk`, `/ai-analyst`, `/paper`) in the frontend.

## 6. AI Analyst panel

The dashboard's own summary (distinct from the full AI Analyst Center at `/ai-analyst`, docs/ai-analyst.md §18): the most recent `ai_analyses` entry's thesis, suggested action, and qualitative uncertainty, matched against its own `signal_id` within the snapshot's `signals` list to show the deterministic signal alongside it. When `system_health.ai.available` is `false`, the panel shows "AI Analyst unavailable — configure the Claude provider to enable analysis." instead — never fake commentary. When the AI's `suggested_action` differs from the matched signal's `signal`, an explicit `ANALYSIS DISAGREEMENT` banner appears — never hidden, never implying either side is authoritative (docs/ai-analyst.md §2).

## 7. Refresh strategy

Controlled polling, not a WebSocket: `CommandCenter.tsx` re-fetches both the snapshot and the chart series every 30 seconds (`REFRESH_INTERVAL_MS`), plus immediately on a symbol/interval change. Chosen over a push channel because nothing about this platform's data changes faster than a human paying attention would notice within 30s — the underlying market data is a mock provider updated on each request, not a real tick stream — and a fixed poll interval is trivially bounded (exactly one snapshot request + one chart request per tick, regardless of how many sections the dashboard shows), avoiding the request-storm risk a naive per-panel polling scheme would have reintroduced. A failed refresh keeps the last-good snapshot on screen with a small inline "Last refresh failed" note (`refreshError` state) rather than clearing the dashboard — only the *initial* load shows the full loading skeleton.

## 8. System Health

`system_health` in the snapshot: `api` (always `"ok"` — the response was produced at all), `database`/`redis` (the same `check_connection()` functions `GET /health/ready` already uses), `market_data` (`"ok"` if at least one watchlist quote succeeded, `"down"` otherwise — reusing the watchlist fetch already made, not a separate probe), and `ai` (exactly `GET /ai/status`'s own shape — `configured`/`available`/`provider`/`model`, never a key or secret). Rendered as a compact status strip — glyph-free here (a colored dot + text label, consistent with `docs/ui-design-system.md` §5's "never color alone" rule via the paired text label) rather than the full `StatusTag` glyph set, since five inline health rows in one small strip favor density over the larger glyph treatment used elsewhere.

## 9. Removed: fabricated dashboard data

`AlertPreview.tsx` (deleted) rendered two hardcoded fake alert rows ("Daily profit target reached +2.1%", specific fake timestamps) — exactly the kind of fabricated production data this phase explicitly forbids. Alerts is not part of the Command Center's required section list (Phase 11's own domain, not yet built); rather than keep presenting invented data, the card is gone. The Recent Activity feed (§5) — real, backend-derived events — is the honest replacement for "what happened recently."

## 10. Testing

- **`tests/test_api_command_center.py`** — full snapshot shape, unknown-symbol 404, unsupported-interval 422, watchlist partial-failure skip (and the resulting `market_data: "ok"` health), recent-activity sort order and cap, known event types only, no secret fields in `system_health.ai`, default watchlist/symbol behavior.
- **`tests/commandCenter.test.tsx`** — loading, full render across every section from one snapshot, whole-request failure, empty states (no signals / no activity / no open positions), AI unavailable (no fabricated commentary), AI thesis/action/uncertainty rendering (no fabricated numeric confidence), AI/signal disagreement banner, system health rendering including a down dependency.

## 11. Limitations

- No push channel — a change made by another client is visible within one poll interval (≤30s), not instantly.
- The watchlist remains a fixed/query-param symbol list, matching every prior phase's precedent — no `GET /watchlists` backend exists yet (Phase 1 sketch only).
- `MarketStateVisualization` accepts pre-fetched `data` (Phase 9 addition) to avoid a duplicate request when embedded in the Command Center, but still supports its original self-fetching mode for any future standalone use elsewhere.
