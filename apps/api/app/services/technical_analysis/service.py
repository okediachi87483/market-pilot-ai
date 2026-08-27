"""TechnicalAnalysisService — the composition point between market data
and the calculation engine (Step 2, Step 9).

Calculates on demand from already-persisted `market_data`; does not
persist its own output. See docs/technical-analysis.md
§"Persistence decision" for the full reasoning — in short: indicators are
cheap, deterministic, pure functions of data that's already durable, so
persisting a derived copy would only add staleness/versioning risk for
no real benefit at this data volume (capped at MarketDataService's
existing 2000-bar request limit).
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.errors import ValidationAppError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.services.market_data.service import MarketDataService
from app.services.technical_analysis.engine import Candle, IndicatorSeries, TechnicalAnalysisEngine
from app.services.technical_analysis.features import MarketFeatures, extract_features
from app.services.technical_analysis.regime import RegimeResult, classify_regime

logger = get_logger(__name__)

# Wider than market-data's own default history window (docs/market-data.md
# §9) so a default request reliably clears MIN_CANDLES_FOR_FEATURES for
# every interval, not just the ones with a long default window already.
_DEFAULT_ANALYSIS_WINDOW: dict[str, timedelta] = {
    "1m": timedelta(hours=4),
    "5m": timedelta(hours=12),
    "15m": timedelta(days=2),
    "1h": timedelta(days=10),
    "1d": timedelta(days=365),
}


@dataclass
class AnalysisSnapshot:
    asset: Asset
    interval: str
    source: str
    calculated_at: datetime
    candle_count: int
    latest_timestamp: datetime
    latest_close: float
    series: IndicatorSeries
    index: int
    features: MarketFeatures
    regime: RegimeResult


class TechnicalAnalysisService:
    def __init__(self, market_data_service: MarketDataService) -> None:
        self.market_data_service = market_data_service
        self.engine = TechnicalAnalysisEngine()

    async def _get_candles(
        self,
        symbol: str,
        interval: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[Asset, list[Candle], str]:
        resolved_end = end or datetime.now(UTC)
        resolved_start = start or (
            resolved_end - _DEFAULT_ANALYSIS_WINDOW.get(interval, timedelta(days=30))
        )
        # get_history validates the interval and persists any missing
        # range before returning — see docs/market-data.md.
        asset, rows = await self.market_data_service.get_history(
            symbol, interval=interval, start=resolved_start, end=resolved_end
        )
        # Decimal -> float at this boundary: indicator math is analytical
        # (statistical smoothing, not owed amounts), so float is the
        # correct and standard choice here — see docs/technical-analysis.md
        # §"Numerical considerations". The persisted Decimal values
        # themselves are untouched; this conversion is local to analysis.
        candles = [
            Candle(
                timestamp=row.timestamp,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            for row in rows
        ]
        source = rows[0].source if rows else "mock"
        return asset, candles, source

    async def get_snapshot(
        self, symbol: str, *, interval: str = "1d", end: datetime | None = None
    ) -> AnalysisSnapshot:
        started = time.monotonic()
        asset, candles, source = await self._get_candles(symbol, interval, end=end)
        if not candles:
            raise ValidationAppError(
                "no market data available for the requested range",
                details={"symbol": symbol, "interval": interval},
            )

        series = self.engine.calculate(candles)
        index = series.latest_index()
        assert index is not None
        features = extract_features(series, index)
        regime = classify_regime(features, len(candles))

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "technical analysis calculated symbol=%s interval=%s candles=%d "
            "duration_ms=%.1f regime=%s",
            asset.symbol,
            interval,
            len(candles),
            duration_ms,
            regime.regime,
        )

        return AnalysisSnapshot(
            asset=asset,
            interval=interval,
            source=source,
            calculated_at=datetime.now(UTC),
            candle_count=len(candles),
            latest_timestamp=candles[-1].timestamp,
            latest_close=candles[-1].close,
            series=series,
            index=index,
            features=features,
            regime=regime,
        )

    async def get_series(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[Asset, IndicatorSeries, str]:
        asset, candles, source = await self._get_candles(symbol, interval, start=start, end=end)
        series = self.engine.calculate(candles)
        return asset, series, source
