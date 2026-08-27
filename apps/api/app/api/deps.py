from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.market_data import MarketDataService
from app.services.technical_analysis import TechnicalAnalysisService


async def get_market_data_service(db: AsyncSession = Depends(get_db)) -> MarketDataService:
    return MarketDataService(db)


async def get_technical_analysis_service(
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> TechnicalAnalysisService:
    return TechnicalAnalysisService(market_data_service)
