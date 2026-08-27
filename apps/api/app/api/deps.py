from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.market_data import MarketDataService


async def get_market_data_service(db: AsyncSession = Depends(get_db)) -> MarketDataService:
    return MarketDataService(db)
