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

Full design: [docs/architecture.md](docs/architecture.md) (start here), plus [docs/data-flow.md](docs/data-flow.md), [docs/market-data.md](docs/market-data.md), [docs/technical-analysis.md](docs/technical-analysis.md), [docs/signal-engine.md](docs/signal-engine.md), [docs/risk-engine.md](docs/risk-engine.md), [docs/paper-trading.md](docs/paper-trading.md), [docs/ai-analyst.md](docs/ai-analyst.md), [docs/command-center.md](docs/command-center.md), [docs/database.md](docs/database.md), [docs/api.md](docs/api.md), [docs/ui-design-system.md](docs/ui-design-system.md), and the rest of [docs/](docs/), including [architecture decision records](docs/decisions/).

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

## Production architecture (AWS)

Phase 9.5 deploys the same application — unmodified architecture, same containers, same Alembic migrations — to AWS: ECS Fargate (api + web) behind one Application Load Balancer, RDS PostgreSQL and ElastiCache Redis in private subnets with no internet route, ECR with immutable image tags, Secrets Manager for `POSTGRES_PASSWORD`/`AI_PROVIDER_API_KEY` (never in the task definition or a log), CloudWatch logs/alarms, and GitHub Actions deploying via OIDC (no long-lived AWS keys). One ALB serves both services from one origin, so the frontend calls the API same-origin — no wildcard CORS. Optional Route 53/ACM for a real domain; the stack runs over plain HTTP on the ALB's own DNS name without one. Terraform (`infrastructure/terraform/`) is the infrastructure source of truth.

**Live**: `http://marketpilot-prod-alb-1177715901.us-east-1.elb.amazonaws.com` — full market-data → analysis → signal → risk → paper-trade pipeline verified against this URL. Phase 9.6 re-verified the deployment end to end (zero Terraform drift, security groups/IAM/secrets re-audited live, all CloudWatch alarms OK) and hit three genuine environmental blockers it stopped at rather than faking: no GitHub remote/`gh` CLI (CI/CD implemented, never executed), no domain (HTTPS ready, not active), no real Claude API key (wiring verified, AI Analyst inactive). See [docs/aws-deployment.md](docs/aws-deployment.md) §0/§10 for the exact status of each.

Full detail: [docs/infrastructure.md](docs/infrastructure.md) (architecture, networking, security, cost) and [docs/aws-deployment.md](docs/aws-deployment.md) (bootstrap, deploy flow, rollback, runbook).

## Current phase

**Phase 9 — MarketPilot Command Center.** The `/dashboard` route is rebuilt as the primary operational dashboard, driven by one new aggregated read endpoint (`GET /api/v1/command-center`) instead of the ~10 separate per-panel requests the previous dashboard made — a genuinely new endpoint, but a pure, read-only composition of the same services every other router already depends on, with no new domain logic or table. Eight sections, hierarchy-ordered (the market overview + chart + Market State instrument visually dominate; AI Analyst/Risk/Paper Portfolio sit as an equal-weight secondary row; Active Signals and Recent Activity follow): Market Overview, Market State, Active Signals, AI Analyst, Risk Overview, Paper Portfolio, Recent Activity, and System Health (API/database/redis/market data/AI provider). Every value is real backend data or an explicit unavailable/empty state — the old `AlertPreview` component, which rendered two hardcoded fake alert rows, is deleted along with every other superseded single-purpose preview card (`RiskPreview`, `PortfolioPreview`, `SignalPreview`, `WatchlistPreview`, `AIAnalystPreview`, `MarketStatusPreview`). Polls every 30 seconds, not a WebSocket, at this scale. Full detail: [docs/command-center.md](docs/command-center.md).

Phase 9.5 (production readiness audit + AWS deployment, done out of the original roadmap order — see below) hardened the paper-trading and risk-evaluation write paths against genuine concurrency races, fixed a since-Phase-2 Docker healthcheck defect, and deployed the platform to AWS.

## Upcoming phases

10. Portfolio analytics
11. Alerting + profit protection
12. Backtesting
13. Test coverage expansion
14. Observability (Prometheus/Grafana)
15. CI/CD (GitHub Actions) — the GitHub Actions pipeline itself now exists (`.github/workflows/`, Phase 9.5), built alongside AWS deployment since one doesn't make sense without the other; broader CI/CD scope (branch protection policy, staging environment) remains here.

See [docs/architecture.md](docs/architecture.md) for the full roadmap and rationale.
