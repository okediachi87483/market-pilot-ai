from fastapi import APIRouter, Depends, Query

from app.api.deps import get_market_data_service
from app.schemas.asset import AssetRead
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
async def list_assets(
    asset_type: str | None = Query(None, description="Filter by asset type, e.g. 'equity'"),
    service: MarketDataService = Depends(get_market_data_service),
) -> list[AssetRead]:
    assets = await service.list_assets(asset_type=asset_type)
    return [AssetRead.model_validate(asset) for asset in assets]


@router.get("/{symbol}", response_model=AssetRead)
async def get_asset(
    symbol: str,
    service: MarketDataService = Depends(get_market_data_service),
) -> AssetRead:
    asset = await service.get_asset(symbol)
    return AssetRead.model_validate(asset)
