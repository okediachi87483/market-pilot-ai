# MarketPilot AI

An AI-powered market intelligence and paper-trading platform: continuous market monitoring, technical signals, AI-assisted analysis, a deterministic risk engine, and a simulated portfolio — presented through an "AI market command center" dashboard.

> **This version is paper-trading infrastructure only and does not execute real financial transactions.** There is no brokerage integration, no real order execution, and no real-money withdrawal anywhere in this codebase. See [docs/decisions/ADR-007-paper-trading-first.md](docs/decisions/ADR-007-paper-trading-first.md).

## Architecture overview

Modular monolith: one FastAPI backend composed of independently-owned packages, one Next.js frontend, PostgreSQL as the only durable store, Redis for caching and pub/sub. The pipeline is a one-way pipe with exactly one supervised gate — the deterministic risk engine sits between AI analysis and any simulated trade, and AI output can never bypass it.

```
Market Data -> Normalization -> Technical Analysis -> Signal Engine
   -> AI Analysis -> Risk Engine -> Paper Trading -> Portfolio -> Alerting -> Dashboard
```

Full design: [docs/architecture.md](docs/architecture.md) (start here), plus [docs/data-flow.md](docs/data-flow.md), [docs/ai-architecture.md](docs/ai-architecture.md), [docs/risk-engine.md](docs/risk-engine.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/ui-design-system.md](docs/ui-design-system.md), and the rest of [docs/](docs/), including [architecture decision records](docs/decisions/).

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

python -m pytest -v          # tests
python -m ruff check .       # lint
python -m ruff format .      # format
python -m mypy app           # type-check
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

`packages/` (the domain packages — `market_data`, `technical_analysis`, `signal_engine`, `ai_engine`, `risk_engine`, `paper_trading`, `portfolio`, `alerts`, `backtesting`, `audit`) is intentionally not present yet: Phase 2 is foundation only, and each package is created with real content when its owning phase begins, rather than as an empty placeholder. See [docs/architecture.md](docs/architecture.md) §4 and the Phase 2 completion report for the full reasoning.

## Current phase

**Phase 2 — Foundation.** A fully runnable local development environment: Next.js shell with all twelve routes, FastAPI with health/readiness checks and the `/api/v1` namespace boundary, PostgreSQL and Redis wired for connectivity (no domain schema yet), Docker Compose, structured logging, and CI-ready lint/type-check/test tooling for both apps.

## Upcoming phases

3. Market data ingestion (mock provider) + normalization
4. Technical indicators
5. Deterministic signal engine
6. Deterministic risk engine
7. Paper trading (simulated brokerage)
8. AI analyst (Claude-based, schema-validated, risk-gated)
9. MarketPilot Command Center — full data-wired UI
10. Portfolio analytics
11. Alerting + profit protection
12. Backtesting
13. Test coverage expansion
14. Observability (Prometheus/Grafana)
15. CI/CD (GitHub Actions)
16. AWS deployment (Terraform — not provisioned without explicit approval)

See [docs/architecture.md](docs/architecture.md) for the full roadmap and rationale.
