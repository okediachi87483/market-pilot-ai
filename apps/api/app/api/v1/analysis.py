from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_technical_analysis_service
from app.core.errors import ValidationAppError
from app.models.market_data import SUPPORTED_INTERVALS
from app.schemas.analysis import (
    AnalysisResponse,
    IndicatorPoint,
    IndicatorSeriesResponse,
    IndicatorsResponse,
    MarketFeaturesResponse,
    MomentumIndicators,
    PriceInfo,
    RegimeEndpointResponse,
    RegimeResponse,
    TrendIndicators,
    VolatilityIndicators,
    VolumeIndicators,
)
from app.services.technical_analysis import TechnicalAnalysisService
from app.services.technical_analysis.engine import IndicatorSeries
from app.services.technical_analysis.features import MarketFeatures

router = APIRouter(prefix="/analysis", tags=["analysis"])

_DEFAULT_SERIES_WINDOW: dict[str, timedelta] = {
    "1m": timedelta(hours=4),
    "5m": timedelta(hours=12),
    "15m": timedelta(days=2),
    "1h": timedelta(days=10),
    "1d": timedelta(days=365),
}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_interval(interval: str) -> None:
    if interval not in SUPPORTED_INTERVALS:
        raise ValidationAppError(
            f"unsupported interval: {interval!r}",
            details={"interval": interval, "supported": list(SUPPORTED_INTERVALS)},
        )


def _indicators_at(series: IndicatorSeries, index: int) -> IndicatorsResponse:
    return IndicatorsResponse(
        trend=TrendIndicators(
            sma20=series.sma20[index],
            sma50=series.sma50[index],
            sma200=series.sma200[index],
            ema9=series.ema9[index],
            ema21=series.ema21[index],
            ema50=series.ema50[index],
            ema200=series.ema200[index],
        ),
        momentum=MomentumIndicators(
            rsi14=series.rsi14[index],
            macd=series.macd[index],
            macd_signal=series.macd_signal[index],
            macd_histogram=series.macd_histogram[index],
            stochastic_k=series.stochastic_k[index],
            stochastic_d=series.stochastic_d[index],
        ),
        volatility=VolatilityIndicators(
            atr14=series.atr14[index],
            bollinger_upper=series.bollinger_upper[index],
            bollinger_middle=series.bollinger_middle[index],
            bollinger_lower=series.bollinger_lower[index],
            bollinger_width=series.bollinger_width[index],
        ),
        volume=VolumeIndicators(
            volume=series.volume[index],
            volume_sma=series.volume_sma[index],
            relative_volume=series.relative_volume[index],
        ),
    )


def _features_response(features: MarketFeatures) -> MarketFeaturesResponse:
    return MarketFeaturesResponse(
        price_above_ema21=features.price_above_ema21,
        ema9_above_ema21=features.ema9_above_ema21,
        ema21_above_ema50=features.ema21_above_ema50,
        ema50_above_ema200=features.ema50_above_ema200,
        trend_alignment_score=features.trend_alignment_score,
        trend_alignment_label=features.trend_alignment_label,
        trend_direction=features.trend_direction,
        rsi_state=features.rsi_state,
        macd_state=features.macd_state,
        volume_state=features.volume_state,
        volatility_state=features.volatility_state,
    )


@router.get("/{symbol}", response_model=AnalysisResponse)
async def get_analysis(
    symbol: str,
    interval: str = Query("1d", description="One of: " + ", ".join(SUPPORTED_INTERVALS)),
    service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
) -> AnalysisResponse:
    _validate_interval(interval)
    snapshot = await service.get_snapshot(symbol, interval=interval)

    return AnalysisResponse(
        symbol=snapshot.asset.symbol,
        asset_id=snapshot.asset.id,
        interval=snapshot.interval,
        source=snapshot.source,
        is_mock=snapshot.source == "mock",
        calculated_at=snapshot.calculated_at,
        candle_count=snapshot.candle_count,
        price=PriceInfo(timestamp=snapshot.latest_timestamp, close=snapshot.latest_close),
        indicators=_indicators_at(snapshot.series, snapshot.index),
        features=_features_response(snapshot.features),
        regime=RegimeResponse(regime=snapshot.regime.regime, reasons=snapshot.regime.reasons),
    )


@router.get("/{symbol}/indicators", response_model=IndicatorSeriesResponse)
async def get_indicator_series(
    symbol: str,
    interval: str = Query("1d", description="One of: " + ", ".join(SUPPORTED_INTERVALS)),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
) -> IndicatorSeriesResponse:
    _validate_interval(interval)

    resolved_end = _as_utc(end) if end else datetime.now(UTC)
    resolved_start = _as_utc(start) if start else resolved_end - _DEFAULT_SERIES_WINDOW[interval]
    if resolved_start > resolved_end:
        raise ValidationAppError(
            "start must be <= end",
            details={"start": resolved_start.isoformat(), "end": resolved_end.isoformat()},
        )

    asset, series, source = await service.get_series(
        symbol, interval=interval, start=resolved_start, end=resolved_end
    )

    points = [
        IndicatorPoint(
            timestamp=series.timestamps[i],
            close=series.close[i],
            sma20=series.sma20[i],
            sma50=series.sma50[i],
            sma200=series.sma200[i],
            ema9=series.ema9[i],
            ema21=series.ema21[i],
            ema50=series.ema50[i],
            ema200=series.ema200[i],
            rsi14=series.rsi14[i],
            macd=series.macd[i],
            macd_signal=series.macd_signal[i],
            macd_histogram=series.macd_histogram[i],
            stochastic_k=series.stochastic_k[i],
            stochastic_d=series.stochastic_d[i],
            atr14=series.atr14[i],
            bollinger_upper=series.bollinger_upper[i],
            bollinger_middle=series.bollinger_middle[i],
            bollinger_lower=series.bollinger_lower[i],
            bollinger_width=series.bollinger_width[i],
            volume=series.volume[i],
            volume_sma=series.volume_sma[i],
            relative_volume=series.relative_volume[i],
        )
        for i in range(len(series))
    ]

    return IndicatorSeriesResponse(
        symbol=asset.symbol,
        asset_id=asset.id,
        interval=interval,
        source=source,
        is_mock=source == "mock",
        start=resolved_start,
        end=resolved_end,
        count=len(points),
        points=points,
    )


@router.get("/{symbol}/regime", response_model=RegimeEndpointResponse)
async def get_regime(
    symbol: str,
    interval: str = Query("1d", description="One of: " + ", ".join(SUPPORTED_INTERVALS)),
    service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
) -> RegimeEndpointResponse:
    _validate_interval(interval)
    snapshot = await service.get_snapshot(symbol, interval=interval)

    return RegimeEndpointResponse(
        symbol=snapshot.asset.symbol,
        asset_id=snapshot.asset.id,
        interval=snapshot.interval,
        calculated_at=snapshot.calculated_at,
        candle_count=snapshot.candle_count,
        regime=snapshot.regime.regime,
        reasons=snapshot.regime.reasons,
    )
