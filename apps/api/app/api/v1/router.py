"""The /api/v1 namespace — see docs/api.md.

Sub-routers are added here as each owning package/service lands. Phase 3
adds the first real domain endpoints: assets and market data.
"""

from fastapi import APIRouter

from app.api.v1.assets import router as assets_router
from app.api.v1.market import router as market_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(assets_router)
api_v1_router.include_router(market_router)


@api_v1_router.get("/")
async def v1_root() -> dict[str, str]:
    return {"namespace": "v1", "status": "ok"}
