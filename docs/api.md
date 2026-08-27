# MarketPilot AI — API Architecture

FastAPI, Pydantic v2 schemas for every request/response, OpenAPI docs auto-generated at `/docs`. Base path: `/api/v1`.

## 1. Conventions

- **Auth**: every endpoint except `/health` requires a bearer token in the MVP's auth scaffolding (single-user; enforcement is permissive in local dev, tightened before any shared deployment — see [security.md](security.md)). Endpoints below list authorization requirements in terms of *what* is required, not the specific mechanism, since full auth is a Phase-2+ implementation detail.
- **Error envelope**: every non-2xx response is `{"error": {"code": "string", "message": "string", "details": {...}}}`. `code` is a stable machine-readable string (e.g. `validation_error`, `not_found`, `risk_rejected`); `message` is human-readable; `details` is optional structured context.
- **Pagination**: list endpoints accept `limit` (default 50, max 200) and `cursor` (opaque, from the previous response's `next_cursor`); responses include `{"items": [...], "next_cursor": "..."|null}`.
- **Idempotency**: `POST /trades` requires an `Idempotency-Key` header; replaying the same key returns the original result rather than creating a duplicate (see [database.md](database.md) §1).
- **Rate limiting**: architecture is prepared (Redis-backed token bucket per user/IP) but permissive by default in the MVP; policy detail in [security.md](security.md).
- **Validation**: request bodies are Pydantic models with explicit types and constraints (e.g. `Decimal` with `gt=0` for quantities); a validation failure returns `422` with `code: validation_error` and per-field detail.

## 2. Endpoints

### Health

| | |
|---|---|
| **GET /health** | Liveness/readiness. No auth. Returns `{"status": "ok", "db": "ok"|"down", "redis": "ok"|"down"}`. `200` if the process is up regardless of dependency state (liveness); dependency state is informational here — see [observability.md](observability.md) for the separate readiness check used by orchestration. |

### Assets — implemented in Phase 3, see [market-data.md](market-data.md) §9

| | |
|---|---|
| **GET /assets** | List assets. Query: `asset_type` (equity/etf/crypto/forex, optional filter). Returns only `active` assets. Response: array of `Asset` (id, symbol, name, asset_type, exchange, currency, active, created_at, updated_at). No auth yet (see [security.md](security.md) — auth scaffolding, not enforced this phase). |
| **GET /assets/{symbol}** | Single asset detail, case-insensitive symbol lookup. `404 not_found` if unknown symbol. |

### Market data — implemented in Phase 3, see [market-data.md](market-data.md) §9

| | |
|---|---|
| **GET /market/{symbol}** | Current quote — the latest `1m` bar as of now, ingested on demand. Response includes `source` and `is_mock: true`. `404 not_found` if the symbol is unknown. |
| **GET /market/{symbol}/history** | OHLCV series. Query: `interval` (1m/5m/15m/1h/1d, default 1d), `start`, `end` (ISO 8601, default window sized per interval). `422 validation_error` if `interval` is unsupported, `start > end`, or the range would exceed the 2000-bar cap. `404 not_found` if the symbol is unknown. |

### Watchlists

| | |
|---|---|
| **GET /watchlists** | Current user's watchlists with items expanded. Auth: owner only. |
| **POST /watchlists** | Create a watchlist. Body: `{name}`. `201` + created resource. `422` if `name` empty. Auth: owner only. |
| **DELETE /watchlists/{id}** | Delete a watchlist (cascades items). `404` if not found or not owned. `204` on success. Auth: owner only. |
| **POST /watchlists/{id}/items** | Add an asset. Body: `{asset_id}`. `409 already_exists` if already present. Auth: owner only. |
| **DELETE /watchlists/{id}/items/{asset_id}** | Remove an asset. `204` on success, `404` if not present. Auth: owner only. |

### Technical analysis — implemented in Phase 4, see [technical-analysis.md](technical-analysis.md) §9

> Deviation from the Phase 1 sketch: this document originally reserved `GET /analysis/{symbol}` for a future *AI* analysis endpoint (§"AI analysis" below, as originally sketched). Phase 4 built the deterministic technical-analysis engine first and claimed this path for it, since it's the more fundamental layer and matches the plan's own pipeline order (technical analysis before AI). A future AI Analyst endpoint (Phase 8) will need a **different** path — `/ai-analysis/{symbol}` is the natural choice — to avoid colliding with this one.

| | |
|---|---|
| **GET /analysis/{symbol}** | Current snapshot: price, all indicators, market features, detected regime. Query: `interval`. `404 not_found` if the symbol is unknown. |
| **GET /analysis/{symbol}/indicators** | Full per-bar indicator time series for charting. Query: `interval`, `start`, `end`. |
| **GET /analysis/{symbol}/regime** | Just the detected regime, its reasons, and candle count — a lighter call than the full snapshot. |

### Signals — implemented in Phase 5, see [signal-engine.md](signal-engine.md) §9

> Deviation from the Phase 1 sketch: `GET /signals/{id}` and `GET /signals/{symbol}` can't coexist at the same path shape (FastAPI can't distinguish a UUID from a ticker at the routing layer). Symbol-scoped listing is folded into `GET /signals`'s `symbol` query parameter instead — the same fix already applied to an analogous ambiguity in Phase 3.

| | |
|---|---|
| **GET /signals** | List signals. Query: `symbol`, `strategy_id`, `status`, `interval` (all optional filters), `limit`. |
| **GET /signals/{id}** | Single signal by UUID, with full reasoning (`reasons`, `supporting_features`, `invalidating_conditions`). `404 not_found` if unknown. |
| **POST /signals/evaluate/{symbol}** | Evaluates `symbol` against the `trend_momentum` strategy right now and returns the resulting `CANDIDATE` signal (existing, deduplicated, or newly created — see `was_newly_created`). No request body. Never executes anything — a read of what the deterministic strategy currently suggests. `404 not_found` if the symbol is unknown; `422 validation_error` if `interval` is unsupported. |

### Paper trading — implemented in Phase 7, see [paper-trading.md](paper-trading.md) §18

> Deviations from the Phase 1 sketch's "Portfolio"/"Positions"/"Trades" sections: (1) everything lives under `/paper/*`, not `/portfolio`, `/positions`, `/trades` — this reflects the single simulated account this MVP actually has (no `users`/multi-portfolio table exists yet, matching every prior phase's single-implicit-user posture), not a resource per authenticated owner. (2) There is no user-submitted `POST /trades` with an arbitrary `{asset_id, side, quantity, order_type, limit_price?}` body — execution is exclusively signal-driven: `POST /paper/execute/{signal_id}` consumes a `RISK_APPROVED` signal and uses the exact quantity the Risk Engine already approved, never a client-supplied quantity or price (paper-trading.md §14/§18 — the Risk Engine remains the only source of position sizing, unchanged from Phase 6). (3) `POST /paper/positions/{symbol}/close` is a direct, non-signal-driven action, added because the sketch had no path to exit a position at all. (4) No `Idempotency-Key` header — idempotency is keyed on `signal_id` itself (a database `UNIQUE` constraint), which is the one identifier that actually determines "was this already executed" in a signal-driven model. (5) `auth: owner only` is dropped from every row below, consistent with every other endpoint in this document under the MVP's permissive local-dev auth scaffolding (§1).

| | |
|---|---|
| **GET /paper/portfolio** | Full portfolio state: starting equity, cash, market value, equity, realized/unrealized/total/daily P/L, peak equity, drawdown %, open position count. |
| **GET /paper/positions** | Query: `status` (`OPEN`/`CLOSED`). Each row includes live `current_price`/`market_value`/`unrealized_pnl` — computed on read, never stored (paper-trading.md §2). |
| **GET /paper/orders** | Query: `symbol`, `status`, `limit`. |
| **GET /paper/orders/{id}** | Single order by UUID. `404` if unknown. |
| **GET /paper/fills** | Query: `symbol`, `order_id`, `limit`. |
| **POST /paper/execute/{signal_id}** | Executes a `RISK_APPROVED` signal as a simulated MARKET BUY. `404` unknown signal; `409` if the signal isn't `RISK_APPROVED` or already has a paper order (idempotency). A `200` with `status: "REJECTED"` and a `rejection_reason` is a normal, successful response (e.g. insufficient cash) — not an error status, the same "a rejection is not an error" principle the Phase 1 sketch itself established for `POST /trades`. |
| **POST /paper/positions/{symbol}/close** | Closes the entire open position for `symbol` as a simulated MARKET SELL. `404` if no open position exists. |

### Risk — implemented in Phase 6, see [risk-engine.md](risk-engine.md) §11

> Deviations from the Phase 1 sketch: (1) the config resource is `RiskPolicy`, not `RiskRules` — versioned and immutable per-row rather than a single mutable row per portfolio, so `PUT /risk/rules` inserts a new version instead of updating in place (risk-engine.md §2). (2) A successful `PUT /risk/rules` does not write a dedicated `AuditLog` entry — the `audit`/`audit_logs` table sketched in Phase 1 isn't built yet (no phase has needed it before now); the policy's own version history *is* the audit trail for configuration changes, and every risk decision's full reasoning is separately preserved in `risk_evaluations` (risk-engine.md §10). (3) Three endpoints added beyond the sketch — `POST /risk/evaluate/{signal_id}`, `GET /risk/evaluations`, `GET /risk/evaluations/{id}` — since evaluating a signal and reading back its audit trail are the actual core of what this phase does.

| | |
|---|---|
| **GET /risk** | Current portfolio state (equity, exposure, drawdown, daily P/L, concurrent positions) alongside the active policy's limits — the read model behind the Risk Center's "Portfolio Risk" panel. Distinct from the endpoint below, which is configuration. |
| **GET /risk/rules** | The active `RiskPolicy`. |
| **PUT /risk/rules** | Creates and activates a new policy version. Body: all ten fields required (no partial update, to avoid an ambiguous merge of safety-critical values). Server-side bounds-checked (e.g. `max_portfolio_exposure_pct` must be `(0, 100]`, `stop_loss_pct` must be `(0, 100)`) — `422` on out-of-bounds or missing values. |
| **POST /risk/evaluate/{signal_id}** | Runs the risk-check pipeline once for a `CANDIDATE` signal, sizing a position and computing stop-loss/take-profit, and transitions the signal to `RISK_APPROVED`/`RISK_REJECTED`. `404` unknown signal; `409` if the signal isn't currently `CANDIDATE` (no re-evaluation in this phase). Never places, fills, or simulates a trade — Phase 7 consumes `RISK_APPROVED` signals. |
| **GET /risk/evaluations** | List risk evaluations. Query: `signal_id`, `decision`, `symbol` (all optional filters), `limit`. |
| **GET /risk/evaluations/{id}** | Single evaluation by UUID, with the full check trail and reasons. `404` if unknown. |

### Alerts

| | |
|---|---|
| **GET /alerts** | Query: `unread_only`, `severity`, pagination. Auth: owner only. |
| **PATCH /alerts/{id}** | Body: `{is_read: true}`. Only field that's ever mutable on an alert. `404` if not found/owned. Auth: owner only. |

### Backtests

| | |
|---|---|
| **GET /backtests** | List the user's backtest runs with status and summary results. Auth: owner only. |
| **POST /backtests** | Body: `{strategy_id, asset_ids[], date_from, date_to}`. `202` — backtests run asynchronously (can be long); response includes the `Backtest` id with `status: pending`, poll `GET /backtests/{id}` for completion. `422` if the date range is invalid or `asset_ids` is empty. Auth: owner only. |

## 3. Deviations from the requested endpoint sketch

- Added `POST /trades` (paper order submission) — the original list had no write path into paper trading, and one is required for the platform to do anything beyond observe.
- Added `POST/DELETE /watchlists/{id}/items` — managing a watchlist's contents needs item-level endpoints; folding this into `PUT /watchlists/{id}` would force clients to resend the full item list for a single add/remove.
- Added `PATCH /alerts/{id}` — alerts need at least a read/unread toggle; there is otherwise no way for the UI to reflect "seen."
- Split `GET /risk` (live exposure) from `GET|PUT /risk/rules` (configuration) — the original list's `GET /risk` and `PUT /risk/rules` implied two different resources under inconsistent paths; this makes the split explicit rather than accidental.

## 4. Typed client

`packages/shared` (backend) defines the Pydantic response models; a generated TypeScript client (OpenAPI → `openapi-typescript` or equivalent) in `packages/shared-types` keeps `apps/web` in sync without hand-maintained duplicate types. Generation runs in CI against the FastAPI OpenAPI schema; a frontend PR that drifts from the current API shape fails type-checking, not silently at runtime.
