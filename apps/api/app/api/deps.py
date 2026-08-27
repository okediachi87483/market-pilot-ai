from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services.ai_analyst.client import ClaudeProvider
from app.services.ai_analyst.engine import AIAnalystEngine
from app.services.ai_analyst.service import AIAnalystService
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


async def get_ai_analyst_engine() -> AIAnalystEngine | None:
    """`None` when no API key is configured (Step 4) — an empty key must
    never crash the application; it just means AI analysis is
    unavailable, checked explicitly by `AIAnalystService`."""
    settings = get_settings()
    if not settings.ai_configured:
        return None
    provider = ClaudeProvider(
        api_key=settings.ai_provider_api_key,  # type: ignore[arg-type]
        model=settings.ai_model,
        max_output_tokens=settings.ai_analyst_max_output_tokens,
        timeout_seconds=settings.ai_analyst_timeout_seconds,
    )
    return AIAnalystEngine(provider, provider_name=settings.ai_provider)


async def get_ai_analyst_service(
    db: AsyncSession = Depends(get_db),
    technical_analysis_service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
    engine: AIAnalystEngine | None = Depends(get_ai_analyst_engine),
) -> AIAnalystService:
    return AIAnalystService(db, technical_analysis_service, engine, get_settings())
