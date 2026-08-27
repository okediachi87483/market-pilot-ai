# MarketPilot AI — Market Data

Phase 3. Builds the ingestion and normalization layer described in [architecture.md](architecture.md) and [data-flow.md](data-flow.md). **All market data in this system is currently MOCK DATA**, generated deterministically for development and testing — never real prices, never live, never a substitute for a real market data provider.

## 1. Architecture

```
MARKET DATA PROVIDER  (MarketDataProvider protocol; today: MockMarketDataProvider)
        │
        ▼
RAW MARKET DATA        (ProviderBar — unvalidated, as the provider produced it)
        │
        ▼
VALIDATOR               (app/services/market_data/validator.py — pure, rejects, never corrects)
        │
        ▼
NORMALIZER               (app/services/market_data/normalizer.py — casing, UTC, decimal precision)
        │
        ▼
POSTGRES                 (assets, market_data — app/models/)
        │
    ┌───┴────┐
    ▼         ▼
MARKET API   FUTURE SIGNAL ENGINE
    │
    ▼
WEB DASHBOARD
```

`MarketDataService` (`app/services/market_data/service.py`) is the sole coordinator of this pipeline — the API layer never touches a provider, the validator, or the ORM directly (Step 8). Reads are **ingest-on-demand, then always answer from Postgres**: a quote/history request first ensures the needed range is persisted (idempotently), then reads it back from the database. The API never hands back unpersisted provider output — this is what lets a future signal engine and the API share one source of truth.

## 2. Provider abstraction

`app/services/market_data/provider.py` defines `MarketDataProvider` as a `Protocol` with three methods: `supported_symbols()`, `get_quote(symbol, as_of=...)`, `get_history(symbol, start=, end=, interval=)`. Everything downstream (validator, normalizer, service, API) depends on this Protocol, never on a concrete class.

**Today's only implementation**: `MockMarketDataProvider` (`mock_provider.py`). **Adding a real provider later** means writing a second class implementing the same Protocol — mapping that provider's actual API responses into `ProviderBar` — and passing it to `MarketDataService(db, provider=RealProvider())`. No change is needed to the validator, normalizer, persistence, or API routers, because none of them import a concrete provider. See [ADR-context in architecture.md §2](architecture.md) principle 6 for the same pattern applied to paper trading's `BrokerAdapter`.

## 3. Mock provider

Deterministic and closed-form: every bar is a pure function of `(symbol, interval, bar index)`, computed via a seeded hash — no shared mutable state, no iteration from an anchor. This means:

- The exact same request always returns byte-identical output (Step 5's determinism requirement).
- Any individual bar can be computed directly, without replaying history — historical queries for arbitrary ranges are cheap.
- Re-ingesting the same range is naturally idempotent at the generation level too (not just at the database layer).

**Fixture symbols** (development/testing only, not real securities data): `AAPL`, `MSFT`, `NVDA`, `AMZN`, `TSLA`. Each has an illustrative base price; a bar's OHLC is derived from two superimposed deterministic sine-wave "trend" components plus a small deterministic "noise" term, giving a realistic-looking walk. An unsupported symbol raises `SymbolNotSupportedError`, translated by the service into a `404 not_found`.

**Supported intervals**: `1m`, `5m`, `15m`, `1h`, `1d` (`app/models/market_data.py:SUPPORTED_INTERVALS`, also enforced as a database `CHECK` constraint).

## 4. Data schema

See [database.md](database.md) for the original design; this section documents what Phase 3 actually implemented, which refines a few names from that initial sketch (below).

### `assets`
`id` (UUID PK) · `symbol` (unique with `asset_type`) · `name` · `asset_type` (`equity`/`etf`/`crypto`/`forex`, CHECK-constrained) · `exchange` (nullable) · `currency` (default `USD`) · `active` (default `true`) · `created_at` · `updated_at`.

### `market_data`
`id` (UUID PK) · `asset_id` (FK → assets, cascade delete) · `timestamp` (UTC) · `open`/`high`/`low`/`close` (`NUMERIC(20,8)`) · `volume` (`NUMERIC(28,10)`) · `source` · `interval` · `created_at`.

Constraints (defense-in-depth alongside application-level validation — see §5): `UNIQUE(asset_id, interval, timestamp, source)`; `CHECK` constraints for `interval` membership, `high >= open/close/low`, `low <= open/close`, all prices `> 0`, `volume >= 0`.

Indexes: `asset_id`, `timestamp`, composite `(asset_id, timestamp)`, and `symbol` on `assets` — matching Step 9's requirement and the primary query patterns (latest bar for an asset, range scan for an asset+interval).

### Naming deviations from the Phase 1 sketch

`docs/database.md` originally sketched `asset_class`/`is_active` (no `updated_at`) on `assets`, and `timeframe`/`ts` on `market_data`. Phase 3's implementation instead uses `asset_type`/`active`/`updated_at` and `interval`/`timestamp` — the exact names requested when this schema was actually built. `docs/database.md` has been updated to match; this is a documentation correction, not a second schema.

## 5. Validation

Pure function, `validate_bar(bar) -> list[str]` (empty = valid). Rejects, never silently corrects:

- `high >= open`, `high >= close`, `high >= low`
- `low <= open`, `low <= close`
- all of `open`/`high`/`low`/`close` `> 0`
- `volume >= 0`
- `timestamp` present and timezone-aware
- `symbol` well-formed (non-empty, matches an allowed character set)
- `interval` is one of the supported set

These same invariants are also `CHECK` constraints in Postgres — a defense-in-depth backstop, not a substitute for validating before persistence (invalid rows are rejected before an insert is even attempted; the constraint exists in case that ever changes).

## 6. Normalization

Runs only on bars that already passed validation. Changes *representation*, never *meaning*:

- `symbol`: stripped, uppercased.
- `timestamp`: converted to UTC if not already (see §7).
- `open`/`high`/`low`/`close`: quantized to 8 decimal places (matching the column's `NUMERIC(20,8)`).
- `volume`: quantized to 10 decimal places (matching `NUMERIC(28,10)`).
- `interval`, `source`: stripped, lowercased.

## 7. Timestamp conventions

**All timestamps are UTC, everywhere, always** — in the database, in the API, in the provider interface. A `ProviderBar` must carry a timezone-aware `datetime`; a naive timestamp is a **validation failure**, not silently assumed to be UTC — ambiguity about what timezone a naive timestamp represents is exactly the kind of "silently corrupt or fix" the validator exists to refuse (Step 4). A timezone-aware timestamp in a non-UTC zone is normalized (converted, not reinterpreted) to UTC.

## 8. Idempotent ingestion

`MarketDataService._persist()` writes via `INSERT ... ON CONFLICT (asset_id, interval, timestamp, source) DO NOTHING`. Re-ingesting a range that's already persisted — whether from a retried request, an overlapping date range, or a scheduler re-running — inserts zero new rows for the bars already present. This is exercised directly in `apps/api/tests/test_market_data_db.py` (re-ingest the same range 3×, row count unchanged) and at the API level in `test_api_market.py` (repeated identical requests return identical bars).

## 9. API endpoints

All under `/api/v1`, full detail in [api.md](api.md) (updated for Phase 3's actual implementation below — the original sketch's endpoints, now real):

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/assets` | List assets. Query: `asset_type` (optional filter). Only `active` assets by default. |
| `GET /api/v1/assets/{symbol}` | Single asset, case-insensitive symbol lookup. `404` if unknown. |
| `GET /api/v1/market/{symbol}` | Current quote — the latest `1m` bar as of now (ingested on demand if the last 5 minutes aren't yet persisted). |
| `GET /api/v1/market/{symbol}/history` | Historical OHLCV. Query: `interval` (default `1d`), `start`, `end` (ISO 8601; default window sized per interval — 2h for `1m`, 8h for `5m`, 1d for `15m`, 7d for `1h`, 180d for `1d`). Capped at 2000 bars per request (`ValidationAppError` if exceeded). |

Every quote/history response includes `source` and `is_mock: true` — mock data is never presented as if it were live (Step 12).

### Error handling

Every error response is the standard envelope (`{"error": {"code", "message", "details"}}`, see [api.md](api.md) §1), enforced by handlers registered once in `app/api/error_handlers.py`:

| Situation | Status | `code` |
|---|---|---|
| Unknown symbol | 404 | `not_found` |
| Unsupported interval | 422 | `validation_error` |
| `start > end` | 422 | `validation_error` |
| Malformed query parameter (e.g. unparseable date) | 422 | `validation_error` |
| Requested range exceeds the 2000-bar cap | 422 | `validation_error` |
| Provider failure | 503 | `provider_error` |
| Unexpected/database error | 500 | `internal_error` (logged server-side with the real exception; never a stack trace to the client) |

## 10. Current limitations

- Mock data only — no real provider is connected (deliberately; see Step 19 of the Phase 3 plan).
- Only 5 fixture symbols exist.
- `1d` bars are computed on exact 86400-second boundaries from a fixed anchor, not real trading-calendar days (no weekends/holidays modeling) — irrelevant for a synthetic fixture, would matter for a real provider.
- No background/scheduled ingestion yet — data is ingested on demand when requested, not proactively kept warm. A scheduler is a natural Phase 3+ addition once there's a consumer (e.g. the signal engine) that needs data present without a preceding API call.
- History requests are capped at 2000 bars; there's no pagination for a range larger than that — the caller must split the request.

## 11. Future real-provider integration strategy

1. Implement `MarketDataProvider` for the chosen provider (e.g. a `PolygonMarketDataProvider`), mapping its response shape to `ProviderBar`. This is new code, not a modification to any existing file outside the provider itself.
2. Wire it into `app/api/deps.py`'s `get_market_data_service` (or an environment-driven provider factory) so it's selected by configuration, not a code change.
3. Everything downstream — validation, normalization, the `UNIQUE`/`CHECK` constraints, the API contract, idempotent persistence — already works, because none of it depends on which provider produced the raw bar.
4. Real providers introduce failure modes a deterministic mock never hits (rate limits, partial outages, gaps in historical data, corporate actions). `ProviderError` and the retry-free "fail this request, log it, try again next time" posture in `service.ingest()` are the starting point, not the final design — expect this to grow real backoff/retry policy once it matters.
5. Real provider API keys are secrets — follow [security.md](security.md) §1 (`AI_PROVIDER_API_KEY`'s pattern in `.env.example` is the template: represented architecturally, never required to run the mock-backed system, never committed).
