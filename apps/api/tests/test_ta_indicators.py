"""Pure-math tests for app/services/technical_analysis/indicators.py —
hand-verified examples plus edge cases (insufficient data, flat prices,
zero volume, extreme values, determinism). No FastAPI, no DB.
"""

import math

from app.services.technical_analysis import indicators as ind

# --- SMA ---------------------------------------------------------------


def test_sma_known_values():
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_insufficient_data_returns_all_none():
    assert ind.sma([1, 2], 5) == [None, None]


def test_sma_flat_prices():
    assert ind.sma([10.0, 10.0, 10.0, 10.0], 2) == [None, 10.0, 10.0, 10.0]


def test_sma_is_deterministic():
    values = [1.0, 5.0, 3.0, 9.0, 2.0, 7.0]
    assert ind.sma(values, 3) == ind.sma(values, 3)


# --- EMA ---------------------------------------------------------------


def test_ema_known_values_linear_series():
    # Seed = SMA(3) of [1,2,3] = 2 at index 2; multiplier = 2/4 = 0.5.
    # idx3: (4-2)*0.5+2=3; idx4: (5-3)*0.5+3=4.
    assert ind.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_insufficient_data_returns_all_none():
    assert ind.ema([1.0, 2.0], 5) == [None, None]


def test_ema_flat_prices_stays_flat():
    result = ind.ema([10.0] * 6, 3)
    assert result[2:] == [10.0, 10.0, 10.0, 10.0]


def test_ema_is_deterministic():
    values = [1.0, 5.0, 3.0, 9.0, 2.0, 7.0, 4.0]
    assert ind.ema(values, 3) == ind.ema(values, 3)


# --- RSI -----------------------------------------------------------------


def test_rsi_strictly_increasing_series_is_100():
    closes = [float(10 + i) for i in range(16)]  # no losses at all
    result = ind.rsi(closes, period=14)
    assert result[14] == 100.0


def test_rsi_strictly_decreasing_series_approaches_zero():
    closes = [float(30 - i) for i in range(16)]  # no gains at all
    result = ind.rsi(closes, period=14)
    assert result[14] == 0.0


def test_rsi_flat_prices_is_neutral_fifty():
    closes = [100.0] * 16
    result = ind.rsi(closes, period=14)
    assert result[14] == 50.0


def test_rsi_bounded_between_zero_and_hundred():
    closes = [
        100.0,
        102.0,
        99.0,
        105.0,
        101.0,
        98.0,
        110.0,
        95.0,
        103.0,
        97.0,
        108.0,
        100.0,
        104.0,
        96.0,
        102.0,
    ]
    result = ind.rsi(closes, period=14)
    for value in result:
        if value is not None:
            assert 0.0 <= value <= 100.0


def test_rsi_insufficient_data_returns_all_none():
    assert ind.rsi([1.0, 2.0, 3.0], period=14) == [None, None, None]


def test_rsi_is_deterministic():
    closes = [100.0 + (i % 5) for i in range(30)]
    assert ind.rsi(closes, 14) == ind.rsi(closes, 14)


# --- MACD ------------------------------------------------------------------


def test_macd_insufficient_data_is_all_none():
    closes = [float(i) for i in range(10)]
    macd_line, signal, hist = ind.macd(closes)
    assert macd_line == [None] * 10
    assert signal == [None] * 10
    assert hist == [None] * 10


def test_macd_becomes_defined_after_warmup():
    closes = [100.0 + math.sin(i * 0.3) * 5 for i in range(60)]
    macd_line, signal, hist = ind.macd(closes, fast=12, slow=26, signal=9)
    # MACD line warms up at slow-1=25; signal needs 9 more MACD points.
    assert macd_line[24] is None
    assert macd_line[25] is not None
    assert signal[32] is None
    assert signal[33] is not None
    assert hist[33] == macd_line[33] - signal[33]


def test_macd_is_deterministic():
    closes = [100.0 + (i % 7) * 1.5 for i in range(50)]
    a = ind.macd(closes)
    b = ind.macd(closes)
    assert a == b


# --- Stochastic --------------------------------------------------------


def test_stochastic_known_values():
    highs = [10.0, 12.0, 11.0, 13.0]
    lows = [8.0, 9.0, 9.0, 10.0]
    closes = [9.0, 11.0, 10.0, 12.0]
    k, d = ind.stochastic(highs, lows, closes, period=2, smooth_d=3)
    assert k[1] == 75.0
    assert math.isclose(k[2], 33.333333, rel_tol=1e-4)
    assert k[3] == 75.0
    assert d[0] is None and d[1] is None and d[2] is None
    assert math.isclose(d[3], (75.0 + 33.333333 + 75.0) / 3, rel_tol=1e-4)


def test_stochastic_flat_range_is_neutral_fifty():
    highs = [10.0, 10.0, 10.0]
    lows = [10.0, 10.0, 10.0]
    closes = [10.0, 10.0, 10.0]
    k, _ = ind.stochastic(highs, lows, closes, period=2, smooth_d=2)
    assert k[1] == 50.0


def test_stochastic_bounded_zero_to_hundred():
    highs = [100.0 + i % 3 for i in range(20)]
    lows = [95.0 - i % 2 for i in range(20)]
    closes = [98.0 + (i % 5) for i in range(20)]
    k, d = ind.stochastic(highs, lows, closes, period=5, smooth_d=3)
    for value in k + d:
        if value is not None:
            assert 0.0 <= value <= 100.0


# --- ATR -----------------------------------------------------------------


def test_atr_known_values():
    highs = [10.0, 11.0, 12.0, 13.0]
    lows = [8.0, 9.0, 10.0, 9.0]
    closes = [9.0, 10.0, 11.0, 10.0]
    # TR1 = max(11-9, |11-9|, |9-9|) = 2
    # TR2 = max(12-10, |12-10|, |10-10|) = 2
    # TR3 = max(13-9, |13-11|, |9-11|) = 4
    result = ind.atr(highs, lows, closes, period=2)
    assert result == [None, None, 2.0, 3.0]  # idx2=avg(2,2)=2; idx3=(2*1+4)/2=3


def test_atr_insufficient_data_returns_all_none():
    assert ind.atr([10.0], [9.0], [9.5], period=14) == [None]


def test_atr_zero_when_no_movement():
    highs = lows = closes = [100.0] * 5
    result = ind.atr(highs, lows, closes, period=2)
    assert result[2] == 0.0


def test_atr_is_deterministic():
    highs = [100.0 + i for i in range(20)]
    lows = [95.0 + i for i in range(20)]
    closes = [98.0 + i for i in range(20)]
    assert ind.atr(highs, lows, closes, 14) == ind.atr(highs, lows, closes, 14)


# --- Bollinger Bands -----------------------------------------------------


def test_bollinger_known_values():
    closes = [10.0, 12.0, 10.0, 12.0]
    upper, middle, lower, width = ind.bollinger_bands(closes, period=2, num_std_dev=2.0)
    assert middle[1] == 11.0
    assert upper[1] == 13.0  # 11 + 2*1
    assert lower[1] == 9.0  # 11 - 2*1
    assert math.isclose(width[1], 4 / 11, rel_tol=1e-9)


def test_bollinger_zero_variance_when_flat():
    closes = [10.0] * 5
    upper, middle, lower, width = ind.bollinger_bands(closes, period=2, num_std_dev=2.0)
    assert upper[1] == lower[1] == middle[1] == 10.0
    assert width[1] == 0.0


def test_bollinger_insufficient_data_returns_all_none():
    upper, middle, lower, width = ind.bollinger_bands([1.0, 2.0], period=20)
    assert upper == [None, None]
    assert middle == [None, None]
    assert lower == [None, None]
    assert width == [None, None]


# --- Volume SMA / relative volume ---------------------------------------


def test_volume_sma_matches_sma():
    volumes = [100.0, 200.0, 300.0, 400.0]
    assert ind.volume_sma(volumes, 2) == ind.sma(volumes, 2)


def test_relative_volume_known_values():
    volumes = [100.0, 100.0, 100.0, 300.0]
    vol_sma = ind.volume_sma(volumes, 2)  # [None, 100, 100, 200]
    result = ind.relative_volume(volumes, vol_sma)
    assert result[1] == 1.0
    assert result[3] == 1.5


def test_relative_volume_zero_average_is_none():
    volumes = [0.0, 0.0, 0.0]
    vol_sma = ind.volume_sma(volumes, 2)  # [None, 0.0, 0.0]
    result = ind.relative_volume(volumes, vol_sma)
    assert result[1] is None
    assert result[2] is None


def test_relative_volume_extreme_spike():
    volumes = [100.0, 100.0, 100.0, 10_000_000.0]
    vol_sma = ind.volume_sma(volumes, 2)
    result = ind.relative_volume(volumes, vol_sma)
    assert result[3] == 10_000_000.0 / vol_sma[3]
