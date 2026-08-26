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

### Assets

| | |
|---|---|
| **GET /assets** | List tradable assets. Query: `class` (equity/etf/crypto/forex), `search` (symbol/name substring), pagination. Response: array of `Asset` (id, symbol, class, name, exchange, currency, is_active). Auth: any authenticated user. |
| **GET /assets/{symbol}** | Single asset detail. `404 not_found` if unknown symbol. Auth: any authenticated user. |

### Market data

| | |
|---|---|
| **GET /market/{symbol}** | Latest normalized bar + derived fields (change %, session state). `404` if symbol unknown or has no data yet (`code: no_data`). Auth: any authenticated user. |
| **GET /market/{symbol}/history** | OHLCV series. Query: `timeframe` (1m/5m/1h/1d, default 1d), `from`, `to` (ISO dates, default last 90 days), pagination. `400 validation_error` if `from > to` or range exceeds a configured max (prevents unbounded scans). Auth: any authenticated user. |

### Watchlists

| | |
|---|---|
| **GET /watchlists** | Current user's watchlists with items expanded. Auth: owner only. |
| **POST /watchlists** | Create a watchlist. Body: `{name}`. `201` + created resource. `422` if `name` empty. Auth: owner only. |
| **DELETE /watchlists/{id}** | Delete a watchlist (cascades items). `404` if not found or not owned. `204` on success. Auth: owner only. |
| **POST /watchlists/{id}/items** | Add an asset. Body: `{asset_id}`. `409 already_exists` if already present. Auth: owner only. |
| **DELETE /watchlists/{id}/items/{asset_id}** | Remove an asset. `204` on success, `404` if not present. Auth: owner only. |

### Signals

| | |
|---|---|
| **GET /signals** | Active signals. Query: `asset_class`, `direction`, `min_strength`, pagination. Auth: any authenticated user. |
| **GET /signals/{id}** | Single signal with its supporting/contradicting indicator detail expanded. `404` if not found. Auth: any authenticated user. |

### AI analysis

| | |
|---|---|
| **GET /analysis/{symbol}** | Latest `AIAnalysis` for the asset, in the structured schema defined in [ai-architecture.md](ai-architecture.md). `404 no_analysis` if none exists yet (distinct from `no_data` — the asset may have market data and no analysis if no signal has fired). Auth: any authenticated user. |

### Portfolio

| | |
|---|---|
| **GET /portfolio** | Summary: value, cash, unrealized/realized/daily P/L, total return, exposure %, win rate. Computed via [database.md](database.md) §1's derivation rules, Redis-cached briefly. Auth: owner only. |
| **GET /portfolio/performance** | Equity curve. Query: `range` (1D/1W/1M/3M/1Y/ALL). Auth: owner only. |

### Positions

| | |
|---|---|
| **GET /positions** | Query: `status` (open/closed/all, default open). Auth: owner only. |
| **GET /positions/{id}** | Single position with linked trades. `404` if not found or not owned. Auth: owner only. |

### Trades

| | |
|---|---|
| **GET /trades** | Trade history. Query: `asset_id`, `from`, `to`, pagination. Auth: owner only. |
| **POST /trades** | Submit a paper order (user-initiated). Body: `{asset_id, side, quantity, order_type, limit_price?}`. Requires `Idempotency-Key` header. Flow: validated → passed to the risk engine → `201` with the resulting `Order` (status `filled` or `rejected`, with `risk_decision_reason` always populated) — see [risk-engine.md](risk-engine.md). A rejection is a normal `201`, not an error status: the request was valid and was correctly evaluated, it just wasn't approved. `422` only for malformed input (e.g. non-positive quantity). Auth: owner only. |

### Risk

| | |
|---|---|
| **GET /risk** | Current live exposure vs. configured limits (portfolio-computed: exposure %, daily loss used, drawdown, concurrent position count) — the read model behind the dashboard's Risk panel. Distinct from the endpoint below, which is configuration. Auth: owner only. |
| **GET /risk/rules** | Configured `RiskRules` for the user's portfolio. Auth: owner only. |
| **PUT /risk/rules** | Replace the configured rules. Body: full `RiskRules` payload; all fields required (no partial update, to avoid an ambiguous merge of safety-critical values). Server-side bounds-checked (e.g. `max_portfolio_exposure_pct` must be `(0, 100]`) — `422` on out-of-bounds values. Every successful update writes an `AuditLog` entry. Auth: owner only. |

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
