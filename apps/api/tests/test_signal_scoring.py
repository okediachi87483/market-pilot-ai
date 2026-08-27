from datetime import UTC, datetime

from app.services.signal_engine.scoring import component_scores, strength_from_scores
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


def _input(**feature_overrides) -> SignalInput:
    return SignalInput(
        symbol="AAPL",
        interval="1h",
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        candle_count=200,
        regime=RegimeResult(regime="BULLISH", reasons=["test"]),
        features=_features(**feature_overrides),
        rsi14=55.0,
    )


def test_best_case_scores_maximum_on_every_component():
    scores = component_scores(
        _input(
            trend_alignment_score=2,
            rsi_state="neutral",
            volume_state="elevated",
            volatility_state="normal",
        )
    )
    assert scores == {"trend": 2, "momentum": 2, "volume": 2, "volatility": 2}
    assert strength_from_scores(scores) == "STRONG"


def test_component_scores_are_documented_and_bounded():
    scores = component_scores(_input())
    for value in scores.values():
        assert 0 <= value <= 2


def test_trend_component_reuses_phase4_alignment_score():
    assert component_scores(_input(trend_alignment_score=1))["trend"] == 1
    assert component_scores(_input(trend_alignment_score=2))["trend"] == 2


def test_momentum_component_neutral_scores_higher_than_stretched():
    neutral = component_scores(_input(rsi_state="neutral"))["momentum"]
    overbought = component_scores(_input(rsi_state="overbought"))["momentum"]
    oversold = component_scores(_input(rsi_state="oversold"))["momentum"]
    assert neutral == 2
    assert overbought == 1
    assert oversold == 1


def test_volume_component_elevated_scores_higher_than_normal():
    assert component_scores(_input(volume_state="elevated"))["volume"] == 2
    assert component_scores(_input(volume_state="normal"))["volume"] == 1


def test_volatility_component_normal_scores_higher_than_low():
    assert component_scores(_input(volatility_state="normal"))["volatility"] == 2
    assert component_scores(_input(volatility_state="low"))["volatility"] == 1


def test_strength_boundaries():
    assert strength_from_scores({"a": 1, "b": 1, "c": 1, "d": 1}) == "WEAK"  # total=4
    assert strength_from_scores({"a": 2, "b": 1, "c": 1, "d": 1}) == "MODERATE"  # total=5
    assert strength_from_scores({"a": 2, "b": 2, "c": 1, "d": 1}) == "MODERATE"  # total=6
    assert strength_from_scores({"a": 2, "b": 2, "c": 2, "d": 1}) == "STRONG"  # total=7
    assert strength_from_scores({"a": 2, "b": 2, "c": 2, "d": 2}) == "STRONG"  # total=8


def test_strength_is_always_one_of_the_three_defined_values():
    for trend in (0, 1, 2):
        for momentum in (0, 1, 2):
            for volume in (0, 1, 2):
                for volatility in (0, 1, 2):
                    strength = strength_from_scores(
                        {
                            "trend": trend,
                            "momentum": momentum,
                            "volume": volume,
                            "volatility": volatility,
                        }
                    )
                    assert strength in ("WEAK", "MODERATE", "STRONG")


def test_scoring_is_deterministic():
    signal_input = _input()
    assert component_scores(signal_input) == component_scores(signal_input)
