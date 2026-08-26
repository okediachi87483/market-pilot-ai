# MarketPilot AI — Architecture

Status: Phase 1. Paper trading only. No real brokerage connectivity, no real-money movement, anywhere in this design.

## 1. System overview

MarketPilot AI is a modular monolith: one deployable backend service (FastAPI) composed from independently-owned internal packages, plus one Next.js frontend. It is not a microservices system — see [ADR-001](decisions/ADR-001-modular-monolith-vs-microservices.md) for why.

The system continuously (on a scheduler, not literally real-time in the MVP) pulls market data, normalizes it, computes technical indicators, evaluates deterministic signal rules, asks an LLM to reason over the result, checks any resulting trade suggestion against deterministic risk rules, and — only if approved — books a simulated trade. Portfolio state derived from those trades drives alerting and the dashboard.

The one invariant that shapes every other decision in this document: **the AI layer can suggest, never execute.** Every path from "the AI said something" to "the portfolio changed" is forced through the risk engine, which contains no AI and no non-deterministic logic.

## 2. Architectural principles

1. **Modular monolith, package-per-bounded-context.** Each concern (market data, indicators, signals, AI, risk, paper trading, portfolio, alerts, backtesting, audit) is a physically separate Python package with its own models, service layer, and tests. The FastAPI app imports from packages; packages never import from the app or from each other's internals — only through a package's public `service.py` interface. This gets most of the maintainability benefit of microservices (enforced boundaries, independent testability) without the operational cost (network calls, distributed transactions, service discovery) that an MVP with one operator doesn't need yet. If a package outgrows the monolith later, it can be extracted because the boundary already exists.
2. **The pipeline is a one-way pipe with one supervised gate.** Market data → normalization → indicators → signals → AI analysis → **risk engine** → paper trading → portfolio → alerting → dashboard. Data flows forward. The only component allowed to reject or resize something upstream of it is the risk engine, and it does so deterministically.
3. **Determinism where money is simulated, judgment where markets are interpreted.** Indicators, signals, and risk rules are pure functions of their inputs — same input, same output, always. The AI layer is explicitly the only non-deterministic component, and its blast radius is capped: it can only ever produce an `AIAnalysis` record and a *suggested* action, never a state mutation.
4. **Everything that changes portfolio state is audited.** Every order, every risk decision (approved or rejected, and why), every AI analysis, every alert is written to an append-only audit trail. See [security.md](security.md).
5. **Postgres is the system of record; Redis is disposable.** Nothing is ever true only in Redis. If Redis is flushed, the system loses caching and pub/sub fan-out, not data. See [database.md](database.md) and [data-flow.md](data-flow.md).
6. **Paper trading first, same interfaces as real trading later.** The `paper-trading` package implements a `BrokerAdapter`-shaped interface. A real brokerage integration is a second implementation of that interface, added later, not a rewrite. See [ADR-007](decisions/ADR-007-paper-trading-first.md).

## 3. Major services (packages) and responsibilities

| Package | Responsibility | Depends on |
|---|---|---|
| `market-data` | Adapter interface for price data providers (`MarketDataProvider`); MVP ships `MockMarketDataProvider`, generating clearly-labeled simulated OHLCV bars. Normalizes any provider's payload into the canonical `MarketData` shape (UTC timestamps, asset id, OHLCV, volume). | `shared` |
| `technical-analysis` | Computes indicators (SMA/EMA, RSI, MACD, ATR, VWAP, volume-vs-average) from normalized `MarketData`. Pure functions over time series; no I/O beyond reading `MarketData`, writing `Indicators`. | `market-data`, `shared` |
| `signal-engine` | Deterministic rule set over `Indicators` producing `Signals` (direction, strength, supporting/contradicting indicator ids). No AI, no randomness — same indicator values always produce the same signal. | `technical-analysis`, `shared` |
| `ai-engine` | Calls an LLM (Claude, via a provider-agnostic `AIProvider` interface) with signal + indicator context, and validates the response against a fixed structured schema before persisting it as an `AIAnalysis`. Read-only with respect to everything downstream. | `signal-engine`, `shared` |
| `risk-engine` | Deterministic evaluation of `RiskRules` against current portfolio state and a proposed order. Approves, rejects, or resizes. Contains no LLM calls and no configuration the AI layer can write to. | `portfolio`, `shared` |
| `paper-trading` | Simulated brokerage: order lifecycle, fills, fees, position tracking. Only accepts orders that already carry a risk-engine approval. | `risk-engine`, `shared` |
| `portfolio` | Aggregates positions/trades into value, cash, P/L (realized/unrealized/daily), drawdown, exposure, win rate. Read model for the risk engine and the dashboard. | `paper-trading`, `shared` |
| `alerts` | Evaluates alert conditions (signal-based, risk-threshold-based, profit-protection-based — see [profit-protection.md](profit-protection.md)) and writes `Alerts`. Never executes anything. | `portfolio`, `risk-engine`, `shared` |
| `backtesting` | Replays historical `MarketData` through `technical-analysis` + `signal-engine` + a configured `Strategy` to produce a `Backtest` result, without touching live `paper-trading` state. | `technical-analysis`, `signal-engine`, `shared` |
| `audit` | Single writer for `AuditLogs`. Every other package calls into `audit` to record state-changing actions; nothing writes `audit_logs` directly. | `shared` |
| `shared` | DB session/engine, Redis client, settings/env loading, structured logging, auth primitives, common Pydantic types (e.g. `Money` as `Decimal`). Depended on by everything; depends on nothing else in the repo. | — |

`apps/api` is the composition root: it wires FastAPI routers to package services, owns the scheduler (APScheduler or equivalent, running the ingestion → ... → alerting pipeline on an interval), and owns nothing else — no business logic lives in `apps/api`.

## 4. Folder structure

```
marketpilot-ai/
├── apps/
│   ├── api/                      # FastAPI app — composition root only
│   │   ├── app/
│   │   │   ├── routers/          # thin HTTP layer, one router per resource
│   │   │   ├── scheduler/        # pipeline scheduling (ingest → ... → alert)
│   │   │   ├── main.py
│   │   │   └── deps.py           # DI wiring: routers -> package services
│   │   └── tests/                # API-level (router) tests
│   └── web/                      # Next.js (App Router) + TS + Tailwind
│
├── packages/
│   ├── market_data/
│   ├── technical_analysis/
│   ├── signal_engine/
│   ├── ai_engine/
│   ├── risk_engine/
│   ├── paper_trading/
│   ├── portfolio/
│   ├── alerts/
│   ├── backtesting/
│   ├── audit/
│   └── shared/
│       # each package: models.py, schemas.py, service.py, tests/
│
├── infrastructure/
│   ├── docker/                   # Dockerfiles per app
│   ├── terraform/                # AWS, not applied without explicit approval
│   └── monitoring/               # Prometheus rules, Grafana dashboards
│
├── db/
│   └── migrations/                # Alembic, single migration history across all packages' models
│
├── docs/
│   ├── architecture.md            # this file
│   ├── data-flow.md
│   ├── component-architecture.md
│   ├── database.md
│   ├── api.md
│   ├── ai-architecture.md
│   ├── risk-engine.md
│   ├── profit-protection.md
│   ├── ui-design-system.md
│   ├── ui-screen-map.md
│   ├── security.md
│   ├── observability.md
│   ├── decisions/                 # ADRs
│   └── design/                    # visual design canvas source
│
├── tests/
│   └── e2e/                       # cross-package / cross-service integration tests
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

### Deviations from the sketch provided

- **`packages/*` use underscores, not hyphens** (`market_data` not `market-data`) — required for them to be importable Python packages; this document uses hyphens only in prose for readability.
- **Two packages added: `backtesting` and `audit`.** The requested endpoint list includes `/backtests` and the requested schema includes `audit_logs`; both need an owning package under the "package-per-bounded-context" principle rather than being bolted onto `portfolio` or `shared`.
- **`normalization` folded into `market-data`.** Ingestion and normalization are always exercised together (a provider adapter's whole job is to produce normalized `MarketData`), so splitting them into separate packages would create a boundary with no independent value.
- Everything else matches the requested structure.

## 5. Request flow (synchronous, user-facing)

A dashboard request (e.g. `GET /portfolio`) is: browser → Next.js (server or client fetch) → FastAPI router → `portfolio` package service → Postgres (read), with Redis as a short-TTL read cache for expensive aggregates. No package other than `portfolio` is touched. See [api.md](api.md) for the full endpoint list and [component-architecture.md](component-architecture.md) for how frontend components map to these calls.

## 6. Event / pipeline flow (asynchronous, system-driven)

Run on a scheduled interval by `apps/api`'s scheduler (not per-request):

```
1. market-data      pulls latest bars for every watched asset, writes MarketData
2. technical-analysis   computes Indicators from MarketData
3. signal-engine    evaluates rules over Indicators, writes Signals
4. ai-engine        for each new/changed Signal, calls the LLM, writes AIAnalysis
5. risk-engine       if AIAnalysis.suggested_action implies a trade, evaluates it
                     against RiskRules + current Portfolio -> APPROVED or REJECTED
6. paper-trading     APPROVED suggestions become Orders -> simulated fills -> Trades
7. portfolio         recomputes aggregates from updated Positions/Trades
8. alerts            evaluates alert + profit-protection conditions against
                     the new Portfolio state, writes Alerts
9. audit             every state change in steps 4-8 is written as an AuditLog
                     entry by the package that made it
```

Full sequencing, storage locations, and a Mermaid diagram are in [data-flow.md](data-flow.md). The AI analysis, signal generation, risk validation, paper-trading, and alert flows each get their own detailed walkthrough there and in their dedicated docs ([ai-architecture.md](ai-architecture.md), [risk-engine.md](risk-engine.md), [profit-protection.md](profit-protection.md)).

## 7. Failure scenarios

| Failure | Behavior |
|---|---|
| Market data provider unavailable/errors | Ingestion step for that run is skipped and logged; downstream steps operate on the last known `MarketData`. No fabricated data is ever substituted. |
| AI provider unavailable, times out, or returns a response that fails schema validation | No `AIAnalysis` is written for that signal. The signal still exists and is visible; nothing downstream (risk engine, paper trading) is triggered by it. This is a fail-closed path by construction — the risk engine only reacts to a *validated* `AIAnalysis`, so a missing one simply means no trade is proposed this cycle. |
| Risk engine evaluation errors | Fail closed: the order is rejected, not approved-by-default. An exception in the risk engine must never result in an unchecked trade. |
| Database unavailable | Health/readiness checks fail (see [observability.md](observability.md)); the scheduler pipeline halts rather than operating on stale in-memory state; the API returns 503 for anything requiring a DB read/write. |
| Redis unavailable | Caching and pub/sub degrade silently (cache miss = read Postgres directly); nothing is lost because Redis never holds the only copy of anything. |
| Partial pipeline failure mid-cycle (e.g. signals computed, AI call fails) | Each step commits its own writes; the next scheduled run picks up from current state. Steps are idempotent per (asset, timeframe, timestamp) — re-running a step that already produced output for a given key updates it rather than duplicating it. |

## 8. Security boundaries

Full detail in [security.md](security.md). The boundary that matters architecturally: the AI provider is called with read-only context (signals, indicators, portfolio *summary*, never credentials or write access), and its response is validated against a strict schema before it can influence anything — a malformed or adversarial LLM response is data, not code, and cannot reach the risk engine's decision logic except through the fields that schema defines (see [ai-architecture.md](ai-architecture.md) §"Why the AI cannot bypass risk").

## 9. Scalability considerations

The MVP runs as one API process and one scheduler process (can be the same process locally). Because packages don't share in-process state and only communicate through their service interfaces and the database, the natural scaling path is:

1. **Vertical first** — Postgres and the API process handle MVP load trivially; no premature horizontal scaling.
2. **Scheduler split** — move the pipeline scheduler into its own process/worker once ingestion volume (more assets, shorter intervals) makes it worth decoupling from the API process's request-serving capacity.
3. **Read replicas** — portfolio/dashboard reads are the highest-volume path; a Postgres read replica is the first infra addition if read load becomes a bottleneck, before considering splitting any package into a separate service.
4. **Package extraction, last resort** — if one package (most likely `ai-engine`, due to LLM latency) needs independent scaling or deployment cadence, its already-enforced boundary makes it extractable into its own service without touching the packages that depend on it, since they only ever called its public `service.py` interface.
