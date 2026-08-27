"""Deterministic rule tests for app/services/signal_engine/rules.py.
Every case here is one row of the precedence table documented in
docs/signal-engine.md §"Rules"."""

from datetime import UTC, datetime

from app.services.signal_engine.rules import (
    EXTREME_OVERBOUGHT_RSI,
    EXTREME_OVERSOLD_RSI,
    evaluate_rules,
)
from app.services.signal_engine.types import SignalInput
from app.services.technical_analysis.features import MarketFeatures
from app.services.technical_analysis.regime import RegimeResult


def _features(**overrides) -> MarketFeatures:
    fields = dict(
        price_above_ema21=True,
        ema9_above_ema21=True,
        ema21_above_ema50=True,
        ema50_above_ema200=None,
        trend_alignment_score=2,
        trend_alignment_label="strong",
        trend_direction="bullish",
        rsi_state="neutral",
        macd_state="bullish",
        volume_state="normal",
        volatility_state="normal",
    )
    fields.update(overrides)
    return MarketFeatures(**fields)


def _input(regime: str, *, rsi14: float | None = 55.0, **feature_overrides) -> SignalInput:
    return SignalInput(
        symbol="AAPL",
        interval="1h",
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        candle_count=200,
        regime=RegimeResult(regime=regime, reasons=["test"]),
        features=_features(**feature_overrides),
        rsi14=rsi14,
    )


# --- Strong bullish setup -> BUY ------------------------------------------


def test_strong_bullish_setup_produces_buy():
    result = evaluate_rules(
        _input("BULLISH", rsi14=55.0, macd_state="bullish", volume_state="elevated")
    )
    assert result.signal == "BUY"
    assert len(result.reasons) > 0
    assert len(result.invalidating_conditions) > 0


# --- Bearish setup -> SELL -------------------------------------------------


def test_bearish_setup_produces_sell():
    result = evaluate_rules(
        _input(
            "BEARISH",
            rsi14=45.0,
            macd_state="bearish",
            volume_state="normal",
            trend_direction="bearish",
        )
    )
    assert result.signal == "SELL"
    assert len(result.reasons) > 0
    assert len(result.invalidating_conditions) > 0


# --- Neutral / no-edge regimes -> HOLD -------------------------------------


def test_insufficient_data_regime_is_hold():
    result = evaluate_rules(_input("INSUFFICIENT_DATA"))
    assert result.signal == "HOLD"
    assert result.invalidating_conditions == []


def test_sideways_regime_is_hold():
    result = evaluate_rules(_input("SIDEWAYS"))
    assert result.signal == "HOLD"


def test_high_volatility_regime_is_hold():
    result = evaluate_rules(_input("HIGH_VOLATILITY"))
    assert result.signal == "HOLD"


def test_low_volatility_regime_is_hold():
    result = evaluate_rules(_input("LOW_VOLATILITY"))
    assert result.signal == "HOLD"


# --- Conflicting indicators -> HOLD ----------------------------------------


def test_bullish_regime_with_bearish_macd_is_hold_conflicting_indicators():
    result = evaluate_rules(_input("BULLISH", macd_state="bearish"))
    assert result.signal == "HOLD"
    assert any("conflicting" in r.lower() for r in result.reasons)


def test_bearish_regime_with_bullish_macd_is_hold_conflicting_indicators():
    result = evaluate_rules(_input("BEARISH", macd_state="bullish"))
    assert result.signal == "HOLD"
    assert any("conflicting" in r.lower() for r in result.reasons)


def test_bullish_regime_with_neutral_macd_is_hold():
    result = evaluate_rules(_input("BULLISH", macd_state="neutral"))
    assert result.signal == "HOLD"


# --- Extreme RSI quality filters --------------------------------------


def test_bullish_regime_with_extreme_overbought_rsi_is_hold():
    result = evaluate_rules(_input("BULLISH", rsi14=EXTREME_OVERBOUGHT_RSI + 0.1))
    assert result.signal == "HOLD"
    assert any("overbought" in r.lower() for r in result.reasons)


def test_bullish_regime_with_rsi_exactly_at_extreme_threshold_still_buys():
    # Boundary: > threshold is blocked, == threshold is not.
    result = evaluate_rules(_input("BULLISH", rsi14=EXTREME_OVERBOUGHT_RSI))
    assert result.signal == "BUY"


def test_bearish_regime_with_extreme_oversold_rsi_is_hold():
    result = evaluate_rules(
        _input(
            "BEARISH",
            rsi14=EXTREME_OVERSOLD_RSI - 0.1,
            macd_state="bearish",
            trend_direction="bearish",
        )
    )
    assert result.signal == "HOLD"
    assert any("oversold" in r.lower() for r in result.reasons)


def test_bullish_regime_with_missing_rsi_is_hold():
    result = evaluate_rules(_input("BULLISH", rsi14=None))
    assert result.signal == "HOLD"


# --- Low volume quality filter ------------------------------------------


def test_bullish_regime_with_low_volume_is_hold():
    result = evaluate_rules(_input("BULLISH", volume_state="low"))
    assert result.signal == "HOLD"
    assert any("volume" in r.lower() for r in result.reasons)


def test_bearish_regime_with_low_volume_is_hold():
    result = evaluate_rules(
        _input("BEARISH", volume_state="low", macd_state="bearish", trend_direction="bearish")
    )
    assert result.signal == "HOLD"


# --- Determinism ------------------------------------------------------


def test_identical_inputs_produce_identical_outputs():
    signal_input = _input("BULLISH")
    first = evaluate_rules(signal_input)
    second = evaluate_rules(signal_input)
    assert first == second


def test_changing_one_feature_flips_the_result():
    bullish = evaluate_rules(_input("BULLISH", macd_state="bullish"))
    flipped = evaluate_rules(_input("BULLISH", macd_state="bearish"))
    assert bullish.signal == "BUY"
    assert flipped.signal == "HOLD"
