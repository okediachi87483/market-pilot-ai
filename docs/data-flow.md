# MarketPilot AI — Data Flow

Companion to [architecture.md](architecture.md). This document traces where data lives and moves at each pipeline stage.

## 1. Pipeline overview

```mermaid
flowchart TD
    A[Market Data<br/>market-data package] -->|writes MarketData| PG[(PostgreSQL)]
    A --> B[Data Normalization<br/>same pipeline step]
    B -->|writes MarketData, normalized| PG
    B --> C[Technical Analysis<br/>technical-analysis package]
    C -->|writes Indicators| PG
    C --> D[Signal Engine<br/>signal-engine package]
    D -->|writes Signals| PG
    D --> E[AI Analysis<br/>ai-engine package]
    E -->|reads Signals + Indicators from PG,<br/>calls LLM provider| E
    E -->|writes AIAnalyses| PG
    E --> F{Risk Engine<br/>risk-engine package}
    F -->|reads RiskRules + Portfolio from PG| PG
    F -->|writes RiskDecision to AuditLogs| PG
    F -->|approved| G[Paper Trading<br/>paper-trading package]
    F -->|rejected| N[No trade. AuditLog written.]
    G -->|writes Orders, Trades, Positions| PG
    G --> H[Portfolio<br/>portfolio package]
    H -->|reads Positions/Trades,<br/>writes cached aggregates| RD[(Redis)]
    H --> I[Alerting<br/>alerts package]
    I -->|writes Alerts| PG
    I -->|publishes for live UI push| RD
    I --> J[Dashboard<br/>apps/web]
    J -->|reads via REST API| PG
    J -->|subscribes for near-real-time updates| RD
```

## 2. Where each store is used

### PostgreSQL — system of record

Every entity in [database.md](database.md) lives here and only here: `market_data`, `indicators`, `signals`, `ai_analyses`, `portfolios`, `positions`, `orders`, `trades`, `risk_rules`, `alerts`, `strategies`, `backtests`, `audit_logs`, plus `users`, `assets`, `watchlists`. If Postgres is lost, the system's state is lost — there is no other durable store. Backups and migrations (Alembic) are Postgres-only concerns.

### Redis — disposable cache and fan-out, never the only copy

| Use | Key shape | TTL | What happens if it's empty |
|---|---|---|---|
| Portfolio aggregate cache (value, P/L, exposure) | `portfolio:{portfolio_id}:summary` | 5-15s | Recomputed from Postgres on next read |
| Latest price cache (avoids re-querying `market_data` for every dashboard poll) | `price:{asset_id}:latest` | 5-10s | Read from Postgres instead |
| Pub/sub channel for near-real-time dashboard push (new signal, new alert, price tick) | `channel:signals`, `channel:alerts`, `channel:prices` | n/a (fire-and-forget) | Dashboard falls back to polling REST endpoints |
| Rate-limit counters (API, AI provider calls) | `ratelimit:{scope}:{key}` | window-based | Rate limiting fails open or closed per endpoint policy — see [security.md](security.md) |
| Session / short-lived auth tokens (once auth is implemented beyond MVP scaffolding) | `session:{token}` | session lifetime | User is required to re-authenticate |

Nothing in this table is a source of truth. A `redis-cli FLUSHALL` degrades performance and momentarily breaks live-push, never correctness.

## 3. AI analysis flow (detail)

```mermaid
sequenceDiagram
    participant SE as signal-engine
    participant AE as ai-engine
    participant LLM as Claude (AIProvider)
    participant DB as PostgreSQL

    SE->>DB: write Signal (deterministic)
    AE->>DB: read Signal + related Indicators
    AE->>LLM: structured prompt (symbol, indicators, signal, portfolio summary)
    LLM-->>AE: structured response (see ai-architecture.md schema)
    AE->>AE: validate response against AIAnalysis schema
    alt valid
        AE->>DB: write AIAnalysis (linked to Signal)
    else invalid / timeout / provider error
        AE->>DB: write AuditLog (ai_analysis_failed)
        Note over AE: no AIAnalysis written; pipeline continues without one
    end
```

Full schema and safety rationale: [ai-architecture.md](ai-architecture.md).

## 4. Signal generation flow (detail)

Pure and deterministic — no external calls:

```
Indicators (RSI, MACD, MA cross, volume ratio, ATR, VWAP delta)
    -> rule set (thresholds + combinations, versioned)
    -> Signal { asset_id, direction, strength, supporting_indicator_ids,
                contradicting_indicator_ids, generated_at }
```

Re-running the same rule set against the same `Indicators` row always produces the same `Signal`. Rule versions are recorded on the `Signal` row so historical signals remain reproducible even after the rule set changes.

## 5. Risk validation flow (detail)

```mermaid
flowchart LR
    S[AIAnalysis.suggested_action] --> RE[Risk Engine]
    RE --> C1{Position size <= max?}
    C1 -->|no| REJ[REJECTED]
    C1 -->|yes| C2{Portfolio exposure <= max?}
    C2 -->|no| REJ
    C2 -->|yes| C3{Daily loss < max?}
    C3 -->|no| REJ
    C3 -->|yes| C4{Drawdown < max?}
    C4 -->|no| REJ
    C4 -->|yes| C5{Concurrent positions < max?}
    C5 -->|no| REJ
    C5 -->|yes| C6{Not in post-loss cooldown?}
    C6 -->|no| REJ
    C6 -->|yes| APP[APPROVED -> Order]
    REJ --> AUD[AuditLog: rejection + reason]
    APP --> AUD2[AuditLog: approval + rule trace]
```

Every check is a deterministic comparison against `risk_rules` values and current `portfolio`/`positions` state read from Postgres — no LLM involvement. Full rule definitions: [risk-engine.md](risk-engine.md).

## 6. Paper-trading flow (detail)

```
Approved order -> paper-trading.service.execute_order()
    -> simulate fill at current market price +/- configured slippage model
    -> apply fee schedule (configurable, defaults to a flat or percentage model)
    -> write Trade (fill price, quantity, fees, timestamp)
    -> update or create Position
    -> write AuditLog (trade_executed)
```

No real brokerage API is called anywhere in this path. See [ADR-007](decisions/ADR-007-paper-trading-first.md).

## 7. Alert flow (detail)

```mermaid
flowchart TD
    P[Portfolio state updated] --> AL[alerts package]
    AL --> T1{Daily profit target reached?}
    AL --> T2{Overall profit target reached?}
    AL --> T3{Drawdown threshold reached?}
    AL --> T4{Exposure threshold reached?}
    AL --> T5{Position concentration threshold reached?}
    T1 -->|yes| A1[Alert: PROFIT_TARGET_REACHED]
    T3 -->|yes| A2[Alert: DRAWDOWN_LIMIT_REACHED]
    T4 -->|yes| A3[Alert: EXPOSURE_LIMIT_REACHED]
    A1 --> W[write Alert to PG + publish to Redis channel:alerts]
    A2 --> W
    A3 --> W
    W --> D[Dashboard shows alert; user decides; no automated action]
```

Full threshold design: [profit-protection.md](profit-protection.md). Alerts are always recommendations — the system never withdraws, closes a position, or otherwise acts on an alert without the user initiating the action.

## 8. Audit events

`audit` is the single writer of `audit_logs`. Every step in §1 that changes state calls `audit.service.record(actor, action, entity_type, entity_id, before, after, metadata)` in the same transaction as its own write, so an audit entry can never be silently skipped by a partial commit. Read access to `audit_logs` is exposed read-only; nothing ever updates or deletes an audit row.
