# MarketPilot AI — API

FastAPI backend. Paper-trading infrastructure only — see the repository root [README.md](../../README.md).

## Local development (without Docker)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../../.env.example ../../.env  # if not already created
uvicorn app.main:app --reload --port 8000
```

Requires Postgres and Redis reachable per `.env` — easiest via `docker compose up postgres redis` from the repo root.

## Commands

| Command | Purpose |
|---|---|
| `pytest` | Run tests |
| `ruff check .` | Lint |
| `ruff format .` | Format |
| `mypy app` | Type-check |

## Structure

```
app/
├── api/          HTTP routers — health checks (unversioned) + /api/v1 namespace
├── core/         settings, logging — the only place environment variables are read
├── db/           Postgres + Redis connection management
├── models/       SQLAlchemy models (empty — arrives per-package in Phase 3+)
├── schemas/      Pydantic request/response schemas
├── services/     business logic (empty — arrives per-package in Phase 3+)
└── main.py       app factory, composition root
```

See [docs/architecture.md](../../docs/architecture.md) and [docs/api.md](../../docs/api.md) for the full design this scaffolds.
