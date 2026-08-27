from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services.market_data import MarketDataService
from app.services.paper_trading.execution import ExecutionAdapter, PaperExecutionAdapter
from app.services.paper_trading.service import PaperTradingService
from app.services.risk_engine.portfolio_state import PortfolioStateProvider
from app.services.risk_engine.service import RiskService
from app.services.signal_engine import SignalService
from app.services.technical_analysis import TechnicalAnalysisService


async def get_market_data_service(db: AsyncSession = Depends(get_db)) -> MarketDataService:
    return MarketDataService(db)


async def get_technical_analysis_service(
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> TechnicalAnalysisService:
    return TechnicalAnalysisService(market_data_service)


async def get_signal_service(
    db: AsyncSession = Depends(get_db),
    technical_analysis_service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
) -> SignalService:
    return SignalService(db, technical_analysis_service)


async def get_portfolio_state_provider(
    db: AsyncSession = Depends(get_db),
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> PortfolioStateProvider:
    return PortfolioStateProvider(db, market_data_service)


async def get_risk_service(
    db: AsyncSession = Depends(get_db),
    market_data_service: MarketDataService = Depends(get_market_data_service),
    portfolio_state_provider: PortfolioStateProvider = Depends(get_portfolio_state_provider),
) -> RiskService:
    return RiskService(db, market_data_service, portfolio_state_provider)


async def get_execution_adapter(
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> ExecutionAdapter:
    settings = get_settings()
    return PaperExecutionAdapter(market_data_service, settings.paper_trading_fee_rate)


async def get_paper_trading_service(
    db: AsyncSession = Depends(get_db),
    execution_adapter: ExecutionAdapter = Depends(get_execution_adapter),
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> PaperTradingService:
    return PaperTradingService(db, execution_adapter, market_data_service)
