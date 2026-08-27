# MarketPilot AI

An AI-powered market intelligence and paper-trading platform: continuous market monitoring, technical signals, AI-assisted analysis, a deterministic risk engine, and a simulated portfolio — presented through an "AI market command center" dashboard.

> **This version is paper-trading infrastructure only and does not execute real financial transactions.** There is no brokerage integration, no real order execution, and no real-money withdrawal anywhere in this codebase. See [docs/decisions/ADR-007-paper-trading-first.md](docs/decisions/ADR-007-paper-trading-first.md).
>
> **All market data is currently MOCK DATA.** Prices, quotes, and history come from a deterministic mock provider (`apps/api/app/services/market_data/mock_provider.py`), not a live feed — every API response and UI panel showing market data labels it `SOURCE: MOCK`. See [docs/market-data.md](docs/market-data.md).

## Architecture overview

Modular monolith: one FastAPI backend composed of independently-owned packages, one Next.js frontend, PostgreSQL as the only durable store, Redis for caching and pub/sub. The pipeline is a one-way pipe with exactly one supervised gate — the deterministic risk engine sits between AI analysis and any simulated trade, and AI output can never bypass it.

```
Market Data -> Normalization -> Technical Analysis -> Signal Engine
   -> AI Analysis -> Risk Engine -> Paper Trading -> Portfolio -> Alerting -> Dashboard
```

Full design: [docs/architecture.md](docs/architecture.md) (start here), plus [docs/data-flow.md](docs/data-flow.md), [docs/market-data.md](docs/market-data.md), [docs/technical-analysis.md](docs/technical-analysis.md), [docs/signal-engine.md](docs/signal-engine.md), [docs/risk-engine.md](docs/risk-engine.md), [docs/paper-trading.md](docs/paper-trading.md), [docs/ai-analyst.md](docs/ai-analyst.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/ui-design-system.md](docs/ui-design-system.md), and the rest of [docs/](docs/), including [architecture decision records](docs/decisions/).

> **MarketPilot's AI Analyst provides analytical interpretation only. It does not execute trades, determine position sizing, override risk controls, or access brokerage accounts.** See [docs/ai-analyst.md](docs/ai-analyst.md).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript (strict), Tailwind CSS |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 |
| Cache / pub-sub | Redis 7 |
| Infra | Docker, Docker Compose (local); Terraform + AWS (later, not provisioned without explicit approval) |

## Prerequisites

- Docker and Docker Compose
- Node.js 20+ and npm (only needed for frontend work outside Docker)
- Python 3.12+ (only needed for backend work outside Docker)

## Environment setup

```bash
cp .env.example .env
```

`.env` is git-ignored and never committed — see [docs/security.md](docs/security.md) §1. `.env.example` documents every variable; defaults are safe for local development only.

## Docker setup

```bash
docker compose up --build
```

This starts, in order (via health-check-gated dependencies): **PostgreSQL** → **Redis** → **FastAPI** (`apps/api`) → **Next.js** (`apps/web`).

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API health | http://localhost:8000/health, `/health/live`, `/health/ready` |
| API docs | http://localhost:8000/docs |

Stop everything:

```bash
docker compose down
```

All published ports bind to `127.0.0.1` only (see [docs/security.md](docs/security.md) §5) — the stack is reachable from the host machine, not the network.

## Development commands

Every command below works with or without `make` — see the [Makefile](Makefile) for the wrapped form (`make up`, `make api-test`, etc.).

**Backend** (`apps/api`):

```bash
cd apps/api
python -m venv .venv && source .venv/Scripts/activate   # Windows; macOS/Linux: .venv/bin/activate
python -m pip install -e ".[dev]"

python -m pytest -v          # tests (needs `docker compose up -d postgres redis` for DB-backed tests)
python -m ruff check .       # lint
python -m ruff format .      # format
python -m mypy app           # type-check
python -m alembic upgrade head   # apply migrations
```

**Frontend** (`apps/web`):

```bash
cd apps/web
npm install

npm test                     # tests
npm run lint                 # lint
npm run typecheck            # type-check (tsc --noEmit)
npm run build                # production build
```

## Project structure

```
apps/
├── api/            FastAPI backend — see apps/api/README.md
│   ├── app/services/{market_data,technical_analysis,signal_engine,
│   │                  risk_engine,paper_trading,ai_analyst}/   Phase 3-8 domains
│   └── alembic/                    migrations
└── web/            Next.js frontend — see apps/web/README.md
docs/               architecture, design system, ADRs — see docs/architecture.md
infrastructure/
├── docker/         (reserved — Dockerfiles currently live per-app)
├── terraform/      (reserved — Phase 16+, not applied without explicit approval)
└── monitoring/     (reserved — Prometheus/Grafana config, later phase)
tests/
└── e2e/            (reserved — cross-service integration tests, later phase)
docker-compose.yml
.env.example
Makefile
```

`packages/` (the domain packages — `portfolio`, `alerts`, `backtesting`, `audit`) is intentionally not present yet: each is created with real content when its owning phase begins, rather than as an empty placeholder. Market data, technical analysis, the signal engine, the risk engine, paper trading, and the AI Analyst (Phase 3/4/5/6/7/8's owning domains) live inside `apps/api/app/services/{market_data,technical_analysis,signal_engine,risk_engine,paper_trading,ai_analyst}/` rather than standalone `packages/`, for the same reason — see docs/architecture.md's "do not over-engineer" principle, recorded as a deviation in each phase's completion report. There is also no standalone `portfolio` package (docs/architecture.md §3's deviation note) — Phase 7's `paper_trading` package computes the portfolio state (equity, exposure, P/L, drawdown) both the risk engine and the dashboard need.

## Current phase

**Phase 8 — AI Analyst.** Claude-based analytical interpretation layered over the deterministic pipeline — `SIGNAL ENGINE → AI ANALYST → RISK ENGINE → PAPER TRADING`, with the AI strictly a read-only, parallel consumer of a signal: it cannot execute trades, submit orders, modify positions, modify risk rules or stop-loss/take-profit values, determine position size, or override any Risk Engine decision, not by policy but structurally — its output schema has no field for any of those, and the Risk Engine does not read `AIAnalysis` at all. Claude's structured tool-use forces the response shape; a two-layer validator (schema + content-safety scan) rejects anything malformed, fabricated, or that echoes a prompt-injection attempt before it can ever be persisted. New endpoints: `GET /api/v1/ai/status`, `POST /ai/analyze/{signal_id}`, `GET /ai/analyses` (`GET`, `/{id}`), `GET /ai/signals/{signal_id}`. The `/ai-analyst` route is now a real AI Analyst Center (reusing the Signal Center so the AI's analysis, the deterministic signal, the risk decision, and the paper trade status are always shown together, never in isolation); disagreement between the AI's suggestion and the deterministic signal is always shown explicitly, never hidden; the dashboard shows a real AI preview panel with an explicit "unavailable" state when no provider key is configured. No real broker, no real money, no fabricated confidence. Full detail: [docs/ai-analyst.md](docs/ai-analyst.md).

## Upcoming phases

9. MarketPilot Command Center — full data-wired UI
10. Portfolio analytics
11. Alerting + profit protection
12. Backtesting
13. Test coverage expansion
14. Observability (Prometheus/Grafana)
15. CI/CD (GitHub Actions)
16. AWS deployment (Terraform — not provisioned without explicit approval)

See [docs/architecture.md](docs/architecture.md) for the full roadmap and rationale.
