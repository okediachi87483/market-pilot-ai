"""Deterministic rule evaluation for the `trend_momentum` strategy
(Step 4). Every condition below is documented in docs/signal-engine.md
§"Rules" with the exact same precedence order — read that document
alongside this file, not instead of it.

Combines TREND + VOLATILITY (via the Phase 4 `regime`, which already
encodes both — see the note in rule 3 below), MOMENTUM (MACD state + RSI
extremity), and VOLUME (volume_state) into one precedence-ordered
decision. The first matching rule wins; nothing here computes a
probability or executes anything.
"""

from __future__ import annotations

from app.services.signal_engine.types import RuleOutcome, SignalInput
from app.services.technical_analysis.features import MarketFeatures

# RSI thresholds stricter than Phase 4's own overbought/oversold state
# (70/30) — a signal-quality filter against entering right as a move gets
# extended, distinct from the more permissive "state" thresholds used for
# descriptive purposes in docs/technical-analysis.md.
EXTREME_OVERBOUGHT_RSI = 80.0
EXTREME_OVERSOLD_RSI = 20.0


def evaluate_rules(signal_input: SignalInput) -> RuleOutcome:
    regime = signal_input.regime.regime
    features = signal_input.features
    rsi14 = signal_input.rsi14

    # 1. No directional read is possible at all.
    if regime == "INSUFFICIENT_DATA":
        return RuleOutcome(
            signal="HOLD",
            reasons=["Insufficient market data for a directional signal"],
            invalidating_conditions=[],
        )

    # 2. Regimes with no tradeable directional edge, by design (Step 8's
    # "sideways market" / "extreme volatility" quality filters). Volatility
    # events and low-conviction chop are exactly what these regimes flag —
    # see docs/technical-analysis.md §7 for how they're detected.
    if regime == "SIDEWAYS":
        return RuleOutcome(
            signal="HOLD",
            reasons=["Detected regime is SIDEWAYS — no dominant trend to act on"],
            invalidating_conditions=[],
        )
    if regime == "HIGH_VOLATILITY":
        return RuleOutcome(
            signal="HOLD",
            reasons=[
                "Detected regime is HIGH_VOLATILITY — avoiding entries during a volatility event"
            ],
            invalidating_conditions=[],
        )
    if regime == "LOW_VOLATILITY":
        return RuleOutcome(
            signal="HOLD",
            reasons=["Detected regime is LOW_VOLATILITY — no directional catalyst present"],
            invalidating_conditions=[],
        )

    # 3. BULLISH regime -> candidate BUY, gated by momentum/RSI/volume
    # quality filters (Step 8). Note: because the Phase 4 regime
    # classifier checks HIGH_VOLATILITY before BULLISH/BEARISH
    # (docs/technical-analysis.md §7), reaching this branch already
    # guarantees volatility_state is not "elevated" — so volatility is
    # not re-checked here; it's structurally excluded by the regime gate.
    if regime == "BULLISH":
        if features.macd_state != "bullish":
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    "Regime is BULLISH but MACD does not confirm "
                    f"(macd_state={features.macd_state!r}) — conflicting indicators"
                ],
                invalidating_conditions=[],
            )
        if rsi14 is None:
            return RuleOutcome(
                signal="HOLD",
                reasons=["Regime is BULLISH but RSI is not yet available"],
                invalidating_conditions=[],
            )
        if rsi14 > EXTREME_OVERBOUGHT_RSI:
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    f"Regime is BULLISH but RSI ({rsi14:.1f}) is extremely overbought "
                    f"(> {EXTREME_OVERBOUGHT_RSI:.0f}) — avoiding a late entry"
                ],
                invalidating_conditions=[],
            )
        if features.volume_state == "low":
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    "Regime is BULLISH but volume is low — insufficient participation to "
                    "confirm the move"
                ],
                invalidating_conditions=[],
            )

        return RuleOutcome(
            signal="BUY",
            reasons=_buy_reasons(features, rsi14),
            invalidating_conditions=[
                "Price loses EMA21 support",
                "MACD turns bearish",
                "Detected regime shifts away from BULLISH",
                f"RSI becomes extremely overbought (> {EXTREME_OVERBOUGHT_RSI:.0f}) "
                "without follow-through",
            ],
        )

    # 4. BEARISH regime -> candidate SELL (exit/reduce, not liquidation —
    # see docs/signal-engine.md §"What SELL means"), mirroring rule 3.
    if regime == "BEARISH":
        if features.macd_state != "bearish":
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    "Regime is BEARISH but MACD does not confirm "
                    f"(macd_state={features.macd_state!r}) — conflicting indicators"
                ],
                invalidating_conditions=[],
            )
        if rsi14 is None:
            return RuleOutcome(
                signal="HOLD",
                reasons=["Regime is BEARISH but RSI is not yet available"],
                invalidating_conditions=[],
            )
        if rsi14 < EXTREME_OVERSOLD_RSI:
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    f"Regime is BEARISH but RSI ({rsi14:.1f}) is extremely oversold "
                    f"(< {EXTREME_OVERSOLD_RSI:.0f}) — avoiding a late exit signal"
                ],
                invalidating_conditions=[],
            )
        if features.volume_state == "low":
            return RuleOutcome(
                signal="HOLD",
                reasons=[
                    "Regime is BEARISH but volume is low — insufficient participation to "
                    "confirm the move"
                ],
                invalidating_conditions=[],
            )

        return RuleOutcome(
            signal="SELL",
            reasons=_sell_reasons(features, rsi14),
            invalidating_conditions=[
                "Price reclaims EMA21",
                "MACD turns bullish",
                "Detected regime shifts away from BEARISH",
                f"RSI becomes extremely oversold (< {EXTREME_OVERSOLD_RSI:.0f}) "
                "without follow-through",
            ],
        )

    # Unreachable while `regime` is one of the six documented labels, but
    # fails closed to HOLD rather than raising if that set ever changes.
    return RuleOutcome(
        signal="HOLD", reasons=[f"Unrecognized regime {regime!r}"], invalidating_conditions=[]
    )


def _buy_reasons(features: MarketFeatures, rsi14: float) -> list[str]:
    reasons = [
        "Detected market regime is BULLISH",
        f"Trend alignment is {features.trend_alignment_label} ({features.trend_direction})",
        "MACD is bullish (histogram positive)",
        f"RSI at {rsi14:.1f} ({features.rsi_state}) — not extremely overbought",
    ]
    if features.volume_state == "elevated":
        reasons.append("Volume is elevated, supporting the move")
    else:
        reasons.append("Volume is at/above its recent average")
    return reasons


def _sell_reasons(features: MarketFeatures, rsi14: float) -> list[str]:
    reasons = [
        "Detected market regime is BEARISH",
        f"Trend alignment is {features.trend_alignment_label} ({features.trend_direction})",
        "MACD is bearish (histogram negative)",
        f"RSI at {rsi14:.1f} ({features.rsi_state}) — not extremely oversold",
    ]
    if features.volume_state == "elevated":
        reasons.append("Volume is elevated, supporting the move")
    else:
        reasons.append("Volume is at/above its recent average")
    return reasons
