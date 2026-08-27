# MarketPilot AI — API

FastAPI backend. Paper-trading infrastructure only — see the repository root [README.md](../../README.md).

## Local development (without Docker)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../../.env.example ../../.env  # if not already created
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Requires Postgres and Redis reachable per `.env` — easiest via `docker compose up -d postgres redis` from the repo root. In Docker, migrations run automatically on container start (`docker-entrypoint.sh`).

## Commands

| Command | Purpose |
|---|---|
| `pytest` | Run tests (DB-backed tests auto-skip without a live Postgres) |
| `ruff check .` | Lint |
| `ruff format .` | Format |
| `mypy app` | Type-check |
| `alembic upgrade head` | Apply migrations |
| `alembic revision --autogenerate -m "..."` | Generate a migration from model changes |

## Structure

```
app/
├── api/          HTTP routers — health checks (unversioned) + /api/v1 namespace
├── core/         settings, logging, error types — the only place environment variables are read
├── db/           Postgres + Redis connection management
├── models/       SQLAlchemy models — Asset, MarketData (Phase 3), Signal (Phase 5)
├── schemas/      Pydantic request/response schemas
├── services/
│   ├── market_data/         provider (protocol + mock), validator, normalizer, service (Phase 3)
│   ├── technical_analysis/  indicators, engine, features, regime, service (Phase 4)
│   └── signal_engine/       rules, scoring, engine, risk_boundary, service (Phase 5)
└── main.py       app factory, composition root
alembic/          migrations — see docs/market-data.md §4
```

See [docs/architecture.md](../../docs/architecture.md), [docs/api.md](../../docs/api.md), [docs/market-data.md](../../docs/market-data.md), [docs/technical-analysis.md](../../docs/technical-analysis.md), and [docs/signal-engine.md](../../docs/signal-engine.md) for the full design this implements.

### A note on `mypy` on Windows

If `mypy` fails with `ImportError: DLL load failed ... An Application Control policy has blocked this file`, that's a local Windows security policy blocking mypy's compiled (`mypyc`) binary — not a project issue. Fix locally with a source (pure-Python) reinstall:

```bash
pip install --force-reinstall --no-cache-dir --no-binary mypy mypy==1.13.0
```
