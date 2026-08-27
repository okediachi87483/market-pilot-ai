"""The /api/v1 namespace — see docs/api.md.

Sub-routers are added here as each owning package/service lands. Phase 3
added assets and market data; Phase 4 added technical analysis; Phase 5
added signals; Phase 6 added risk; Phase 7 adds paper trading.
"""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.assets import router as assets_router
from app.api.v1.market import router as market_router
from app.api.v1.paper import router as paper_router
from app.api.v1.risk import router as risk_router
from app.api.v1.signals import router as signals_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(assets_router)
api_v1_router.include_router(market_router)
api_v1_router.include_router(analysis_router)
api_v1_router.include_router(signals_router)
api_v1_router.include_router(risk_router)
api_v1_router.include_router(paper_router)


@api_v1_router.get("/")
async def v1_root() -> dict[str, str]:
    return {"namespace": "v1", "status": "ok"}
