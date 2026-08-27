from app.services.technical_analysis.engine import IndicatorSeries
from app.services.technical_analysis.features import extract_features


def _series(**overrides) -> IndicatorSeries:
    """A one-point IndicatorSeries with every field defaulted to None,
    overridden per test — lets each test isolate the field(s) it cares
    about without constructing a full realistic series."""
    from datetime import UTC, datetime

    fields = {
        "timestamps": [datetime(2024, 1, 1, tzinfo=UTC)],
        "close": [None],
        "sma20": [None],
        "sma50": [None],
        "sma200": [None],
        "ema9": [None],
        "ema21": [None],
        "ema50": [None],
        "ema200": [None],
        "rsi14": [None],
        "macd": [None],
        "macd_signal": [None],
        "macd_histogram": [None],
        "stochastic_k": [None],
        "stochastic_d": [None],
        "atr14": [None],
        "bollinger_upper": [None],
        "bollinger_middle": [None],
        "bollinger_lower": [None],
        "bollinger_width": [None],
        "volume": [None],
        "volume_sma": [None],
        "relative_volume": [None],
    }
    fields.update(overrides)
    return IndicatorSeries(**fields)


# --- Trend alignment truth table ----------------------------------------


def test_trend_alignment_unanimous_bullish_across_all_four_is_strong():
    series = _series(close=[110.0], ema9=[108.0], ema21=[105.0], ema50=[100.0], ema200=[95.0])
    features = extract_features(series, 0)
    assert features.trend_alignment_score == 2
    assert features.trend_alignment_label == "strong"
    assert features.trend_direction == "bullish"


def test_trend_alignment_unanimous_bearish_across_all_four_is_strong():
    series = _series(close=[90.0], ema9=[92.0], ema21=[95.0], ema50=[100.0], ema200=[105.0])
    features = extract_features(series, 0)
    assert features.trend_alignment_score == 2
    assert features.trend_alignment_label == "strong"
    assert features.trend_direction == "bearish"


def test_trend_alignment_majority_not_unanimous_is_partial():
    # price>ema21 (T), ema9>ema21 (T), ema21>ema50 (F) -> 2-1 majority.
    series = _series(close=[110.0], ema9=[108.0], ema21=[105.0], ema50=[106.0])
    features = extract_features(series, 0)
    assert features.trend_alignment_score == 1
    assert features.trend_alignment_label == "partial"
    assert features.trend_direction == "bullish"


def test_trend_alignment_even_split_is_weak():
    # Only 2 checks available (ema50/ema200 both None): price_above_ema21
    # is True (110 > 105) but ema9_above_ema21 is False (100 < 105) — a
    # genuine 1-1 disagreement.
    series = _series(close=[110.0], ema9=[100.0], ema21=[105.0])
    features = extract_features(series, 0)
    assert features.trend_alignment_score == 0
    assert features.trend_alignment_label == "weak"
    assert features.trend_direction == "mixed"


def test_trend_alignment_unanimous_but_only_one_check_available_is_partial():
    series = _series(close=[110.0], ema21=[105.0])  # only price_above_ema21 defined
    features = extract_features(series, 0)
    assert features.trend_alignment_score == 1
    assert features.trend_alignment_label == "partial"


def test_trend_alignment_no_checks_available_is_none():
    series = _series()
    features = extract_features(series, 0)
    assert features.trend_alignment_score is None
    assert features.trend_alignment_label is None
    assert features.trend_direction is None


def test_ema50_above_ema200_reported_even_when_not_part_of_score():
    series = _series(close=[110.0], ema21=[105.0], ema50=[100.0], ema200=[90.0])
    features = extract_features(series, 0)
    assert features.ema50_above_ema200 is True


# --- RSI state -------------------------------------------------------------


def test_rsi_state_thresholds():
    assert extract_features(_series(rsi14=[29.9]), 0).rsi_state == "oversold"
    assert extract_features(_series(rsi14=[30.0]), 0).rsi_state == "neutral"
    assert extract_features(_series(rsi14=[70.0]), 0).rsi_state == "neutral"
    assert extract_features(_series(rsi14=[70.1]), 0).rsi_state == "overbought"
    assert extract_features(_series(rsi14=[None]), 0).rsi_state is None


# --- MACD state --------------------------------------------------------


def test_macd_state_from_histogram_sign():
    assert extract_features(_series(macd_histogram=[0.01]), 0).macd_state == "bullish"
    assert extract_features(_series(macd_histogram=[-0.01]), 0).macd_state == "bearish"
    assert extract_features(_series(macd_histogram=[0.0]), 0).macd_state == "neutral"
    assert extract_features(_series(macd_histogram=[None]), 0).macd_state is None


# --- Volume state ------------------------------------------------------


def test_volume_state_thresholds():
    assert extract_features(_series(relative_volume=[0.5]), 0).volume_state == "low"
    assert extract_features(_series(relative_volume=[1.0]), 0).volume_state == "normal"
    assert extract_features(_series(relative_volume=[1.5]), 0).volume_state == "elevated"
    assert extract_features(_series(relative_volume=[None]), 0).volume_state is None


# --- Volatility state ----------------------------------------------------


def test_volatility_state_thresholds():
    # atr_pct = atr14 / close * 100
    assert extract_features(_series(atr14=[0.5], close=[100.0]), 0).volatility_state == "low"
    assert extract_features(_series(atr14=[2.0], close=[100.0]), 0).volatility_state == "normal"
    assert extract_features(_series(atr14=[5.0], close=[100.0]), 0).volatility_state == "elevated"


def test_volatility_state_none_when_close_is_zero_or_missing():
    assert extract_features(_series(atr14=[1.0], close=[0.0]), 0).volatility_state is None
    assert extract_features(_series(atr14=[None], close=[100.0]), 0).volatility_state is None
