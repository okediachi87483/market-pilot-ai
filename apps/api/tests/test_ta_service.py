"""Integration tests: MarketDataService -> TechnicalAnalysisService,
against a live Postgres. Requires `docker compose up -d postgres redis`
— auto-skipped otherwise (see tests/conftest.py db_engine).

Uses the mock provider's real fixture symbols, same rationale as Phase 3's
market-data tests: MockMarketDataProvider only serves that fixed set.
"""

from datetime import UTC, datetime

import pytest

from app.core.errors import NotFoundError
from app.services.market_data.service import MarketDataService
from app.services.technical_analysis.engine import MIN_CANDLES_FOR_FEATURES
from app.services.technical_analysis.service import TechnicalAnalysisService


@pytest.mark.asyncio
async def test_get_snapshot_with_ample_history(db_session) -> None:
    market_data = MarketDataService(db_session)
    service = TechnicalAnalysisService(market_data)

    snapshot = await service.get_snapshot(
        "AAPL", interval="1d", end=datetime(2030, 6, 1, tzinfo=UTC)
    )

    assert snapshot.asset.symbol == "AAPL"
    assert snapshot.interval == "1d"
    assert snapshot.source == "mock"
    assert snapshot.candle_count >= MIN_CANDLES_FOR_FEATURES
    assert snapshot.features.trend_alignment_score is not None
    assert snapshot.regime.regime != "INSUFFICIENT_DATA"
    assert snapshot.series.sma20[snapshot.index] is not None


@pytest.mark.asyncio
async def test_get_snapshot_calculation_is_deterministic(db_session) -> None:
    market_data = MarketDataService(db_session)
    service = TechnicalAnalysisService(market_data)
    end = datetime(2030, 7, 1, tzinfo=UTC)

    first = await service.get_snapshot("MSFT", interval="1d", end=end)
    second = await service.get_snapshot("MSFT", interval="1d", end=end)

    assert first.series.sma20 == second.series.sma20
    assert first.series.rsi14 == second.series.rsi14
    assert first.regime.regime == second.regime.regime
    assert first.features == second.features


@pytest.mark.asyncio
async def test_get_snapshot_unknown_symbol_raises_not_found(db_session) -> None:
    market_data = MarketDataService(db_session)
    service = TechnicalAnalysisService(market_data)

    with pytest.raises(NotFoundError):
        await service.get_snapshot("NOSUCHSYMBOL")


@pytest.mark.asyncio
async def test_get_series_length_matches_candle_count(db_session) -> None:
    market_data = MarketDataService(db_session)
    service = TechnicalAnalysisService(market_data)

    asset, series, source = await service.get_series(
        "NVDA",
        interval="1h",
        start=datetime(2030, 8, 1, tzinfo=UTC),
        end=datetime(2030, 8, 1, 5, 0, tzinfo=UTC),
    )

    assert asset.symbol == "NVDA"
    assert source == "mock"
    assert len(series) == 6
    assert series.timestamps == sorted(series.timestamps)


@pytest.mark.asyncio
async def test_short_range_leaves_long_period_indicators_none(db_session) -> None:
    market_data = MarketDataService(db_session)
    service = TechnicalAnalysisService(market_data)

    asset, series, _ = await service.get_series(
        "TSLA",
        interval="1h",
        start=datetime(2030, 9, 1, tzinfo=UTC),
        end=datetime(2030, 9, 1, 4, 0, tzinfo=UTC),
    )

    index = series.latest_index()
    assert series.sma200[index] is None
    assert series.ema200[index] is None
