import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.ai import AIAnalysisResponse, AIStatusResponse
from app.schemas.analysis import MarketFeaturesResponse, PriceInfo, RegimeResponse
from app.schemas.paper import PaperFillResponse, PaperPortfolioResponse, PaperPositionResponse
from app.schemas.risk import RiskSummaryResponse
from app.schemas.signal import SignalResponse

# Every field below is either a nested reuse of an existing endpoint's own
# response schema (RiskSummaryResponse, PaperPortfolioResponse, etc.) or a
# small aggregation-only shape defined here (SystemHealthResponse,
# MarketSnapshotResponse, WatchlistQuoteResponse, ActivityEventResponse) —
# this endpoint composes existing service reads, it never recomputes or
# duplicates any domain logic (docs/command-center.md §2).


class SystemHealthResponse(BaseModel):
    api: str  # always "ok" if this response was produced at all
    database: str  # "ok" | "down"
    redis: str  # "ok" | "down"
    market_data: str  # "ok" | "down" — derived from whether any watchlist quote succeeded
    ai: AIStatusResponse


class MarketSnapshotResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    source: str
    is_mock: bool
    calculated_at: datetime
    candle_count: int
    price: PriceInfo
    features: MarketFeaturesResponse
    regime: RegimeResponse


class WatchlistQuoteResponse(BaseModel):
    symbol: str
    close: Decimal
    change_pct: Decimal | None  # derived from the same bar's own open/close — never fabricated
    timestamp: datetime
    source: str
    is_mock: bool


class ActivityEventResponse(BaseModel):
    # One of: SIGNAL_GENERATED, RISK_APPROVED, RISK_REJECTED,
    # AI_ANALYSIS_COMPLETED, PAPER_ORDER_FILLED, POSITION_CLOSED — see
    # docs/command-center.md §5 for exactly how each is derived.
    type: str
    timestamp: datetime
    symbol: str
    summary: str
    signal_id: uuid.UUID | None


class CommandCenterResponse(BaseModel):
    generated_at: datetime
    system_health: SystemHealthResponse
    market: MarketSnapshotResponse
    watchlist: list[WatchlistQuoteResponse]
    signals: list[SignalResponse]
    ai_analyses: list[AIAnalysisResponse]
    risk: RiskSummaryResponse
    portfolio: PaperPortfolioResponse
    positions: list[PaperPositionResponse]
    recent_fills: list[PaperFillResponse]
    recent_activity: list[ActivityEventResponse]
