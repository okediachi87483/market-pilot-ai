import math
from datetime import UTC, datetime, timedelta

from app.services.technical_analysis.engine import Candle, TechnicalAnalysisEngine


def _candles(n: int) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(n):
        close = 100.0 + math.sin(i * 0.2) * 5 + i * 0.05
        candles.append(
            Candle(
                timestamp=start + timedelta(hours=i),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000.0 + (i % 7) * 50_000,
            )
        )
    return candles


def test_calculate_returns_series_aligned_with_input_length():
    candles = _candles(60)
    series = TechnicalAnalysisEngine().calculate(candles)
    assert len(series) == 60
    assert len(series.sma20) == 60
    assert len(series.rsi14) == 60
    assert len(series.bollinger_upper) == 60


def test_calculate_is_deterministic():
    candles = _candles(80)
    engine = TechnicalAnalysisEngine()
    a = engine.calculate(candles)
    b = engine.calculate(candles)
    assert a.sma20 == b.sma20
    assert a.rsi14 == b.rsi14
    assert a.macd == b.macd
    assert a.bollinger_upper == b.bollinger_upper


def test_calculate_with_insufficient_data_has_all_none_indicators():
    candles = _candles(5)
    series = TechnicalAnalysisEngine().calculate(candles)
    assert series.sma20 == [None] * 5
    assert series.ema200 == [None] * 5
    assert series.rsi14 == [None] * 5
    assert series.macd == [None] * 5


def test_calculate_with_ample_data_produces_full_snapshot_at_latest_index():
    candles = _candles(250)
    series = TechnicalAnalysisEngine().calculate(candles)
    index = series.latest_index()
    assert index == 249
    # With 250 candles every indicator (including the 200-period ones)
    # should be defined at the latest bar.
    assert series.sma200[index] is not None
    assert series.ema200[index] is not None
    assert series.rsi14[index] is not None
    assert series.macd[index] is not None
    assert series.macd_signal[index] is not None
    assert series.atr14[index] is not None
    assert series.bollinger_upper[index] is not None
    assert series.relative_volume[index] is not None


def test_latest_index_on_empty_series_is_none():
    series = TechnicalAnalysisEngine().calculate([])
    assert series.latest_index() is None
    assert len(series) == 0


def test_flat_price_series_produces_finite_indicators():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = [
        Candle(
            timestamp=start + timedelta(hours=i),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0.0,
        )
        for i in range(60)
    ]
    series = TechnicalAnalysisEngine().calculate(candles)
    index = series.latest_index()
    assert series.rsi14[index] == 50.0
    assert series.atr14[index] == 0.0
    assert series.bollinger_width[index] == 0.0
    assert series.relative_volume[index] is None  # zero-volume window
