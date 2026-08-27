from datetime import UTC, datetime

from app.services.signal_engine.engine import SignalEngine
from app.services.signal_engine.types import STRATEGY_ID, STRATEGY_VERSION, SignalInput
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


def _input(regime: str, **feature_overrides) -> SignalInput:
    return SignalInput(
        symbol="AAPL",
        interval="1h",
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        candle_count=200,
        regime=RegimeResult(regime=regime, reasons=["test"]),
        features=_features(**feature_overrides),
        rsi14=55.0,
    )


def test_buy_candidate_has_a_strength_and_positive_reasons():
    candidate = SignalEngine().evaluate(_input("BULLISH"))
    assert candidate.signal == "BUY"
    assert candidate.strength in ("WEAK", "MODERATE", "STRONG")
    assert len(candidate.reasons) > 0
    assert len(candidate.invalidating_conditions) > 0


def test_hold_candidate_has_no_strength():
    candidate = SignalEngine().evaluate(_input("SIDEWAYS"))
    assert candidate.signal == "HOLD"
    assert candidate.strength is None
    assert candidate.score_breakdown == {}


def test_candidate_always_carries_strategy_identity():
    candidate = SignalEngine().evaluate(_input("BULLISH"))
    assert candidate.strategy_id == STRATEGY_ID == "trend_momentum"
    assert candidate.strategy_version == STRATEGY_VERSION == "1.0.0"


def test_candidate_status_is_always_candidate():
    for regime in ("BULLISH", "BEARISH", "SIDEWAYS", "INSUFFICIENT_DATA"):
        candidate = SignalEngine().evaluate(
            _input(regime, macd_state="bearish" if regime == "BEARISH" else "bullish")
        )
        assert candidate.status == "CANDIDATE"


def test_candidate_supporting_features_include_the_raw_evidence():
    candidate = SignalEngine().evaluate(_input("BULLISH"))
    assert candidate.supporting_features["regime"] == "BULLISH"
    assert candidate.supporting_features["rsi14"] == 55.0
    assert candidate.supporting_features["macd_state"] == "bullish"


def test_candidate_market_regime_matches_input_regime():
    candidate = SignalEngine().evaluate(
        _input("BEARISH", macd_state="bearish", trend_direction="bearish")
    )
    assert candidate.market_regime == "BEARISH"


def test_repeated_evaluation_with_identical_inputs_is_deterministic():
    signal_input = _input("BULLISH")
    engine = SignalEngine()
    first = engine.evaluate(signal_input)
    second = engine.evaluate(signal_input)
    assert first == second


def test_no_fabricated_probability_anywhere_in_the_candidate():
    candidate = SignalEngine().evaluate(_input("BULLISH"))
    serialized = " ".join(candidate.reasons) + str(candidate.supporting_features)
    assert "%" not in serialized
    assert "chance" not in serialized.lower()
    assert "probability" not in serialized.lower()
