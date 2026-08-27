import uuid
from datetime import datetime

from pydantic import BaseModel


class TrendIndicators(BaseModel):
    sma20: float | None
    sma50: float | None
    sma200: float | None
    ema9: float | None
    ema21: float | None
    ema50: float | None
    ema200: float | None


class MomentumIndicators(BaseModel):
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    stochastic_k: float | None
    stochastic_d: float | None


class VolatilityIndicators(BaseModel):
    atr14: float | None
    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None
    bollinger_width: float | None


class VolumeIndicators(BaseModel):
    volume: float | None
    volume_sma: float | None
    relative_volume: float | None


class IndicatorsResponse(BaseModel):
    trend: TrendIndicators
    momentum: MomentumIndicators
    volatility: VolatilityIndicators
    volume: VolumeIndicators


class MarketFeaturesResponse(BaseModel):
    price_above_ema21: bool | None
    ema9_above_ema21: bool | None
    ema21_above_ema50: bool | None
    ema50_above_ema200: bool | None
    trend_alignment_score: int | None
    trend_alignment_label: str | None
    trend_direction: str | None
    rsi_state: str | None
    macd_state: str | None
    volume_state: str | None
    volatility_state: str | None


class RegimeResponse(BaseModel):
    regime: str
    reasons: list[str]


class PriceInfo(BaseModel):
    timestamp: datetime
    close: float


class AnalysisResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    source: str
    is_mock: bool
    calculated_at: datetime
    candle_count: int
    price: PriceInfo
    indicators: IndicatorsResponse
    features: MarketFeaturesResponse
    regime: RegimeResponse


class IndicatorPoint(BaseModel):
    timestamp: datetime
    close: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    ema9: float | None
    ema21: float | None
    ema50: float | None
    ema200: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    stochastic_k: float | None
    stochastic_d: float | None
    atr14: float | None
    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None
    bollinger_width: float | None
    volume: float | None
    volume_sma: float | None
    relative_volume: float | None


class IndicatorSeriesResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    source: str
    is_mock: bool
    start: datetime
    end: datetime
    count: int
    points: list[IndicatorPoint]


class RegimeEndpointResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    calculated_at: datetime
    candle_count: int
    regime: str
    reasons: list[str]
