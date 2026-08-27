from app.services.technical_analysis.engine import MIN_CANDLES_FOR_FEATURES
from app.services.technical_analysis.features import MarketFeatures
from app.services.technical_analysis.regime import classify_regime


def _features(**overrides) -> MarketFeatures:
    fields = dict(
        price_above_ema21=None,
        ema9_above_ema21=None,
        ema21_above_ema50=None,
        ema50_above_ema200=None,
        trend_alignment_score=None,
        trend_alignment_label=None,
        trend_direction=None,
        rsi_state=None,
        macd_state=None,
        volume_state=None,
        volatility_state=None,
    )
    fields.update(overrides)
    return MarketFeatures(**fields)


def test_insufficient_candle_count_wins_regardless_of_features():
    features = _features(
        trend_alignment_score=2, trend_direction="bullish", volatility_state="normal"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES - 1)
    assert result.regime == "INSUFFICIENT_DATA"


def test_missing_trend_alignment_score_is_insufficient_data_even_with_enough_candles():
    features = _features(trend_alignment_score=None)
    result = classify_regime(features, candle_count=1000)
    assert result.regime == "INSUFFICIENT_DATA"


def test_elevated_volatility_wins_over_trend():
    features = _features(
        trend_alignment_score=2, trend_direction="bullish", volatility_state="elevated"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "HIGH_VOLATILITY"


def test_low_volatility_and_weak_trend_is_low_volatility_regime():
    features = _features(trend_alignment_score=0, trend_direction="mixed", volatility_state="low")
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "LOW_VOLATILITY"


def test_low_volatility_with_strong_trend_is_not_low_volatility_regime():
    # Volatility is low, but trend alignment is strong (not weak) — rule 3
    # requires both low volatility AND weak alignment.
    features = _features(trend_alignment_score=2, trend_direction="bullish", volatility_state="low")
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "BULLISH"


def test_bullish_trend_with_normal_volatility_is_bullish_regime():
    features = _features(
        trend_alignment_score=1, trend_direction="bullish", volatility_state="normal"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "BULLISH"


def test_bearish_trend_with_normal_volatility_is_bearish_regime():
    features = _features(
        trend_alignment_score=1, trend_direction="bearish", volatility_state="normal"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "BEARISH"


def test_weak_alignment_with_normal_volatility_is_sideways():
    features = _features(
        trend_alignment_score=0, trend_direction="mixed", volatility_state="normal"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "SIDEWAYS"


def test_mixed_direction_with_partial_alignment_falls_through_to_sideways():
    # trend_alignment_score >= 1 but direction is "mixed" (a tie) — not
    # actually possible from _trend_direction/_trend_alignment together in
    # practice, but the classifier should not misclassify it as bullish or
    # bearish if it occurs.
    features = _features(
        trend_alignment_score=1, trend_direction="mixed", volatility_state="normal"
    )
    result = classify_regime(features, candle_count=MIN_CANDLES_FOR_FEATURES)
    assert result.regime == "SIDEWAYS"


def test_regime_result_always_has_reasons():
    cases = [
        (10, _features()),
        (
            100,
            _features(
                trend_alignment_score=2, trend_direction="bullish", volatility_state="elevated"
            ),
        ),
        (
            100,
            _features(trend_alignment_score=0, trend_direction="mixed", volatility_state="low"),
        ),
        (
            100,
            _features(
                trend_alignment_score=1, trend_direction="bullish", volatility_state="normal"
            ),
        ),
        (
            100,
            _features(
                trend_alignment_score=1, trend_direction="bearish", volatility_state="normal"
            ),
        ),
        (
            100,
            _features(trend_alignment_score=0, trend_direction="mixed", volatility_state="normal"),
        ),
    ]
    for candle_count, features in cases:
        result = classify_regime(features, candle_count)
        assert len(result.reasons) >= 1
        assert all(isinstance(r, str) and r for r in result.reasons)
