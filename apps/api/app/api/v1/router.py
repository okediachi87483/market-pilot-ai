"""The /api/v1 namespace — see docs/api.md.

This is the architectural boundary for versioned business endpoints
(assets, market, watchlists, signals, analysis, portfolio, positions,
trades, risk, alerts, backtests). None of those exist yet: each is added
here as `api_v1_router.include_router(...)` when its owning package
lands in Phase 3+. Business logic is intentionally not implemented in
Phase 2 — this router only proves the versioning architecture works.
"""

from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")


@api_v1_router.get("/")
async def v1_root() -> dict[str, str]:
    return {"namespace": "v1", "status": "foundation — no domain endpoints yet"}
