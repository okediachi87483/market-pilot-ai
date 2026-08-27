# MarketPilot AI — Database Architecture

PostgreSQL 16. Managed via Alembic migrations, one linear history across all packages' models (package boundaries are a Python/import concern, not a schema-per-package concern — the database is one coherent whole). No destructive raw SQL; no hard-coded credentials, connection info via environment variables only (see [security.md](security.md)).

## 1. Financial data integrity — read this before the schema

- **No floats for money, price, or quantity, anywhere** — not in the database, not in Python, not in JSON responses that a client might parse and re-sum. All monetary and quantity columns are `NUMERIC` (Postgres exact decimal), mapped to Python's `Decimal` in SQLAlchemy/Pydantic models, never `float`.
- **Price precision**: `NUMERIC(20,8)`. Eight fractional digits covers equities/ETFs/forex (2-6 places) and crypto (up to 8 places) with one column type across `assets` of every class, avoiding a precision special-case per asset class.
- **Quantity precision**: `NUMERIC(28,10)`. Ten fractional digits so fractional-share equities and fractional crypto quantities (e.g. `0.00000042` BTC) are representable exactly.
- **Fees**: stored as their own `NUMERIC(20,8)` column on `trades`, never netted into `fill_price` — the fill price is always the true execution price; fees are always visible and auditable separately.
- **P/L**: never stored as a single mutable running total that gets edited in place. Realized P/L is derived from closed `trades` (sum of `(exit - entry) * quantity - fees`, computed in Postgres or the `portfolio` service, both using `Decimal`/`NUMERIC` arithmetic); unrealized P/L is derived on read from open `positions` against the latest `market_data` price. `portfolios.cash` is the one balance that *is* stored and updated, and every update to it is paired with a `trades` row and an `audit_logs` row that justify the delta — it is never edited independently.
- **Timestamps**: `TIMESTAMPTZ`, always stored and compared in UTC. Every table that represents an event (`market_data`, `signals`, `ai_analyses`, `trades`, `alerts`, `audit_logs`) has an explicit event timestamp separate from row-creation bookkeeping where the two could differ (e.g. a backfilled `market_data` row).
- **Idempotency**: `orders.idempotency_key` is a unique, not-null column. The scheduler and any client-initiated order submission generate a deterministic key (e.g. `{signal_id}:{rule_version}` for system-generated orders, a client-supplied UUID for user-initiated ones) so a retried request or a re-run pipeline cycle cannot create a duplicate order/trade. A duplicate submission is rejected with the existing order's id, not silently re-executed.
- **Auditability**: every table that represents money or a decision (`orders`, `trades`, `risk_rules` changes, `positions` changes) has a corresponding `audit_logs` entry written in the same transaction as the change (see [security.md](security.md) and [architecture.md](architecture.md) §4/§8). `audit_logs` rows are never updated or deleted — enforced at the application layer now, and at the database role/grant level before production.

## 2. Entity-relationship overview

```mermaid
erDiagram
    users ||--o{ watchlists : owns
    users ||--o{ portfolios : owns
    users ||--o{ alerts : receives
    users ||--o{ strategies : authors
    watchlists ||--o{ watchlist_items : contains
    assets ||--o{ watchlist_items : referenced_by
    assets ||--o{ market_data : has
    assets ||--o{ indicators : has
    assets ||--o{ signals : has
    assets ||--o{ positions : held_as
    signals ||--o{ ai_analyses : analyzed_by
    portfolios ||--|| risk_rules : governed_by
    portfolios ||--o{ positions : holds
    portfolios ||--o{ orders : places
    orders ||--o| trades : fills_into
    strategies ||--o{ backtests : evaluated_by
```

## 3. Table definitions

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `email` | TEXT UNIQUE NOT NULL | |
| `password_hash` | TEXT | nullable in MVP scaffolding until auth is fully wired — see [security.md](security.md) |
| `display_name` | TEXT | |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL | |

### `assets`

> Implemented in Phase 3 as `asset_type`/`active`/`updated_at` rather than this document's original `asset_class`/`is_active` (no `updated_at`) sketch — the names below are what actually shipped (`apps/api/app/models/asset.py`); see [market-data.md](market-data.md) §4.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `symbol` | TEXT NOT NULL | e.g. `NVDA`, `BTC-USD`, `EUR/USD` |
| `asset_type` | TEXT NOT NULL | CHECK IN (`equity`,`etf`,`crypto`,`forex`) |
| `name` | TEXT | |
| `exchange` | TEXT | nullable (not meaningful for forex/crypto pairs) |
| `currency` | TEXT NOT NULL DEFAULT `'USD'` | |
| `active` | BOOLEAN NOT NULL DEFAULT `true` | soft-disable without deleting history |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL | |
| Constraints | `UNIQUE(symbol, asset_type)` | |

### `watchlists` / `watchlist_items`
| Table | Column | Type | Notes |
|---|---|---|---|
| `watchlists` | `id` | UUID PK | |
| | `user_id` | FK → `users.id` NOT NULL | |
| | `name` | TEXT NOT NULL | |
| | `created_at`, `updated_at` | TIMESTAMPTZ | |
| `watchlist_items` | `id` | UUID PK | |
| | `watchlist_id` | FK → `watchlists.id` NOT NULL | |
| | `asset_id` | FK → `assets.id` NOT NULL | |
| | `added_at` | TIMESTAMPTZ NOT NULL | |
| | Constraints | `UNIQUE(watchlist_id, asset_id)` | |

### `market_data`

> Implemented in Phase 3 as `interval`/`timestamp` rather than this document's original `timeframe`/`ts` sketch, and with a UUID PK (matching every other table) rather than BIGSERIAL — see [market-data.md](market-data.md) §4.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `asset_id` | FK → `assets.id` NOT NULL, `ON DELETE CASCADE` | |
| `interval` | TEXT NOT NULL | CHECK IN (`1m`,`5m`,`15m`,`1h`,`1d`) |
| `timestamp` | TIMESTAMPTZ NOT NULL | bar timestamp (open time), UTC |
| `open`,`high`,`low`,`close` | NUMERIC(20,8) NOT NULL | CHECK `high >= open/close/low`, `low <= open/close`, all `> 0` |
| `volume` | NUMERIC(28,10) NOT NULL | CHECK `>= 0` |
| `source` | TEXT NOT NULL | provider id; MVP value is always `mock` — see [market-data.md](market-data.md) §9 note on labeled mock data |
| Constraints | `UNIQUE(asset_id, interval, timestamp, source)` | prevents duplicate bars on re-ingestion — idempotent ingestion, see [market-data.md](market-data.md) §8 |
| Indexes | `asset_id`, `timestamp`, composite `(asset_id, timestamp)` | primary query pattern: latest N bars for an asset/interval |

### `indicators`
| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `asset_id` | FK → `assets.id` NOT NULL | |
| `timeframe` | TEXT NOT NULL | |
| `ts` | TIMESTAMPTZ NOT NULL | |
| `name` | TEXT NOT NULL | e.g. `RSI_14`, `MACD`, `ATR_14`, `SMA_50`, `VWAP_DELTA` |
| `value` | NUMERIC(20,8) NOT NULL | |
| `metadata` | JSONB | secondary fields for multi-value indicators (e.g. MACD signal/histogram) |
| Constraints | `UNIQUE(asset_id, timeframe, ts, name)` | |
| Indexes | `(asset_id, name, ts DESC)` | |

### `signals`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `asset_id` | FK → `assets.id` NOT NULL | |
| `direction` | TEXT NOT NULL | CHECK IN (`long`,`short`,`neutral`) |
| `strength` | NUMERIC(5,2) NOT NULL | 0-100, deterministic rule score |
| `rule_version` | TEXT NOT NULL | reproducibility — see §1 |
| `supporting_indicator_ids` | JSONB NOT NULL | array of `indicators.id` |
| `contradicting_indicator_ids` | JSONB NOT NULL | |
| `status` | TEXT NOT NULL DEFAULT `'active'` | CHECK IN (`active`,`superseded`,`expired`) |
| `generated_at` | TIMESTAMPTZ NOT NULL | |
| Indexes | `(asset_id, generated_at DESC)`, `(status)` | |

### `ai_analyses` — superseded by Phase 8, see [ai-analyst.md](ai-analyst.md) §10

> The sketch below (kept for historical reference) had `market_state`/`trend`/`momentum`/`volume_assessment` enums, a numeric `confidence NUMERIC(5,2)`, `suggested_action` as `long`/`short`/`hold`/`close`/`none`, and price-level fields (`entry_zone_*`, `stop_loss`, `take_profit_*`). None of that shipped: the as-built table has no numeric confidence field at all (only a qualitative `uncertainty` LOW/MEDIUM/HIGH enum) and no price-level fields whatsoever — those never leave the Risk Engine. `suggested_action` is `BUY`/`SELL`/`HOLD`/`NO_ACTION`, matching Phase 5's own `Signal.signal` vocabulary. Full as-built schema: ai-analyst.md §10.

### `ai_analyses` (Phase 1 sketch — see note above)
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `signal_id` | FK → `signals.id` NOT NULL | |
| `asset_id` | FK → `assets.id` NOT NULL | denormalized for direct query without a join |
| `market_state`,`trend`,`momentum`,`volume_assessment` | TEXT NOT NULL | enumerations — see [ai-architecture.md](ai-architecture.md) schema |
| `supporting_indicators`,`conflicting_indicators` | JSONB NOT NULL | |
| `thesis` | TEXT NOT NULL | hedged natural-language rationale |
| `invalidation_conditions` | TEXT NOT NULL | |
| `risk_level` | TEXT NOT NULL | CHECK IN (`low`,`moderate`,`high`) |
| `confidence` | NUMERIC(5,2) NOT NULL | CHECK `BETWEEN 0 AND 100` |
| `suggested_action` | TEXT NOT NULL | CHECK IN (`long`,`short`,`hold`,`close`,`none`) |
| `entry_zone_low`,`entry_zone_high` | NUMERIC(20,8) | nullable when action is `hold`/`none` |
| `stop_loss` | NUMERIC(20,8) | nullable |
| `take_profit_low`,`take_profit_high` | NUMERIC(20,8) | nullable |
| `model_name`,`model_version`,`prompt_version` | TEXT NOT NULL | reproducibility/auditability of AI output |
| `generated_at` | TIMESTAMPTZ NOT NULL | |
| Indexes | `(asset_id, generated_at DESC)`, `(signal_id)` | |

### `portfolios`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → `users.id` NOT NULL | |
| `name` | TEXT NOT NULL | |
| `cash` | NUMERIC(20,8) NOT NULL | see §1 — the one directly-updated balance |
| `mode` | TEXT NOT NULL DEFAULT `'paper'` | CHECK IN (`paper`) in the MVP — reserved value, no other mode is enabled by application logic |
| `created_at`,`updated_at` | TIMESTAMPTZ | |

### `positions`, `orders`, `trades` — superseded by Phase 7, see [paper-trading.md](paper-trading.md) §2

> This sketch (below, kept for historical reference) assumed a `portfolios`/`users` table that was never built — every prior phase (3 through 8) has stayed single-implicit-user, with no auth or multi-portfolio system yet. What Phase 7 actually shipped is `paper_accounts` (one row, replacing `portfolios.cash`), `paper_positions`, `paper_orders`, and `paper_fills` (replacing `trades`) — no `portfolio_id` anywhere, `orders.limit_price`/`idempotency_key` replaced by `signal_id UNIQUE` (execution is signal-driven, not user-submitted with an arbitrary price). Phase 8 (now built — see [ai-analyst.md](ai-analyst.md) §10) did not add an `ai_analysis_id` column to `paper_orders` either: a paper order's execution is driven exclusively by `RiskEvaluation`/`Signal`, never by an `AIAnalysis`, so there is no relationship for such a column to express. Full current schema: paper-trading.md §2.

### `positions` (Phase 1 sketch — see note above)
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | FK → `portfolios.id` NOT NULL | |
| `asset_id` | FK → `assets.id` NOT NULL | |
| `side` | TEXT NOT NULL | CHECK IN (`long`,`short`) |
| `quantity` | NUMERIC(28,10) NOT NULL | |
| `avg_entry_price` | NUMERIC(20,8) NOT NULL | |
| `realized_pl` | NUMERIC(20,8) NOT NULL DEFAULT 0 | accumulated on partial closes |
| `status` | TEXT NOT NULL DEFAULT `'open'` | CHECK IN (`open`,`closed`) |
| `opened_at` | TIMESTAMPTZ NOT NULL | |
| `closed_at` | TIMESTAMPTZ | nullable |
| Constraints | `UNIQUE(portfolio_id, asset_id) WHERE status = 'open'` | one open position per asset per portfolio in the MVP — a documented simplification, not a schema limitation for the future |
| Indexes | `(portfolio_id, status)` | |

### `orders` (Phase 1 sketch — see note above)
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | FK → `portfolios.id` NOT NULL | |
| `asset_id` | FK → `assets.id` NOT NULL | |
| `side` | TEXT NOT NULL | CHECK IN (`buy`,`sell`) |
| `order_type` | TEXT NOT NULL DEFAULT `'market'` | CHECK IN (`market`,`limit`) |
| `quantity` | NUMERIC(28,10) NOT NULL | |
| `limit_price` | NUMERIC(20,8) | nullable, required when `order_type = 'limit'` |
| `idempotency_key` | TEXT NOT NULL UNIQUE | see §1 |
| `signal_id` | FK → `signals.id` | nullable — null for user-initiated orders not tied to a signal |
| `ai_analysis_id` | FK → `ai_analyses.id` | nullable |
| `risk_decision` | TEXT NOT NULL | CHECK IN (`approved`,`rejected`) |
| `risk_decision_reason` | TEXT NOT NULL | human-readable rule trace |
| `status` | TEXT NOT NULL DEFAULT `'pending'` | CHECK IN (`pending`,`filled`,`rejected`,`cancelled`) |
| `created_at`,`updated_at` | TIMESTAMPTZ | |

### `trades` (Phase 1 sketch — see note above)
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `order_id` | FK → `orders.id` NOT NULL UNIQUE | one fill per order in the MVP (no partial fills yet) |
| `portfolio_id` | FK → `portfolios.id` NOT NULL | denormalized for query convenience |
| `asset_id` | FK → `assets.id` NOT NULL | |
| `side` | TEXT NOT NULL | |
| `quantity` | NUMERIC(28,10) NOT NULL | |
| `fill_price` | NUMERIC(20,8) NOT NULL | true execution price, never fee-adjusted — see §1 |
| `fees` | NUMERIC(20,8) NOT NULL DEFAULT 0 | |
| `executed_at` | TIMESTAMPTZ NOT NULL | |
| Indexes | `(portfolio_id, executed_at DESC)` | |

### `risk_rules` — superseded by Phase 6's `risk_policies`, see [risk-engine.md](risk-engine.md) §2/§3

> Renamed and re-modeled in Phase 6: versioned, immutable rows (`PUT /risk/rules` inserts a new version rather than updating `portfolio_id`'s single row — there is no `portfolio_id` column at all, matching the single-account posture noted above) plus a `risk_evaluations` audit table. Kept below for historical reference only.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | FK → `portfolios.id` NOT NULL UNIQUE | one active rule set per portfolio in the MVP |
| `max_position_size_pct` | NUMERIC(5,2) NOT NULL | |
| `max_portfolio_exposure_pct` | NUMERIC(5,2) NOT NULL | |
| `max_daily_loss_pct` | NUMERIC(5,2) NOT NULL | |
| `max_drawdown_pct` | NUMERIC(5,2) NOT NULL | |
| `default_stop_loss_pct` | NUMERIC(5,2) NOT NULL | |
| `default_take_profit_pct` | NUMERIC(5,2) NOT NULL | |
| `max_concurrent_positions` | INTEGER NOT NULL | |
| `cooldown_after_loss_minutes` | INTEGER NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Full rule semantics: [risk-engine.md](risk-engine.md).

### `alerts`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → `users.id` NOT NULL | |
| `portfolio_id` | FK → `portfolios.id` | nullable (some alerts, e.g. a signal alert, aren't portfolio-scoped) |
| `type` | TEXT NOT NULL | e.g. `PROFIT_TARGET_REACHED`, `DRAWDOWN_LIMIT_REACHED`, `EXPOSURE_LIMIT_REACHED`, `SIGNAL_GENERATED`, `INVALIDATION_APPROACHING` — full list in [profit-protection.md](profit-protection.md) |
| `severity` | TEXT NOT NULL | CHECK IN (`info`,`warning`,`critical`) |
| `message` | TEXT NOT NULL | |
| `metadata` | JSONB | structured detail (threshold, actual value, related entity ids) |
| `is_read` | BOOLEAN NOT NULL DEFAULT `false` | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| Indexes | `(user_id, created_at DESC)` | |

### `strategies`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → `users.id` NOT NULL | |
| `name` | TEXT NOT NULL | |
| `rule_config` | JSONB NOT NULL | parameterization of signal rules for backtesting |
| `created_at`,`updated_at` | TIMESTAMPTZ | |

### `backtests`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `strategy_id` | FK → `strategies.id` NOT NULL | |
| `asset_ids` | JSONB NOT NULL | array of `assets.id` |
| `date_from`,`date_to` | DATE NOT NULL | |
| `status` | TEXT NOT NULL DEFAULT `'pending'` | CHECK IN (`pending`,`running`,`completed`,`failed`) |
| `results` | JSONB | summary metrics once completed: total return, win rate, max drawdown, trade count, profit factor |
| `created_at`,`completed_at` | TIMESTAMPTZ | |

### `audit_logs`
| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL PK | append-only, high-volume |
| `actor` | TEXT NOT NULL | `system`, `user:{id}`, `ai-engine`, `risk-engine`, etc. |
| `action` | TEXT NOT NULL | e.g. `order_approved`, `order_rejected`, `trade_executed`, `risk_rules_updated`, `ai_analysis_failed` |
| `entity_type` | TEXT NOT NULL | e.g. `order`, `trade`, `risk_rules` |
| `entity_id` | TEXT NOT NULL | polymorphic reference, stored as text to stay entity-type-agnostic |
| `before` | JSONB | nullable — state prior to the change |
| `after` | JSONB | nullable — state after the change |
| `metadata` | JSONB | nullable — free-form context (e.g. rule trace, request id) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT `now()` | |
| Indexes | `(entity_type, entity_id)`, `(created_at DESC)` | |
| Constraints | no application code path performs `UPDATE`/`DELETE` on this table; enforced at the database role/grant level before production |

## 4. Migration policy

One Alembic history at `db/migrations/`, shared across all packages. Each package's `models.py` contributes to a single SQLAlchemy metadata object; Alembic autogenerate diffs against that combined metadata. Migrations are additive-first (new nullable columns, new tables) in normal development; destructive migrations (drop column, tighten constraint) require a written justification in the migration's docstring and are never auto-applied in CI without review.
