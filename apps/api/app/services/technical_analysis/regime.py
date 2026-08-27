"""Deterministic, rule-based market-regime classification (Step 7). No
LLM involvement anywhere in this module. A regime is a *detected*
descriptive label for current conditions — never a guarantee of future
direction; callers should present it that way (see docs/technical-analysis.md
§"Market regime" and docs/ai-architecture.md's hedged-language convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.technical_analysis.engine import MIN_CANDLES_FOR_FEATURES
from app.services.technical_analysis.features import MarketFeatures

Regime = Literal[
    "BULLISH", "BEARISH", "SIDEWAYS", "HIGH_VOLATILITY", "LOW_VOLATILITY", "INSUFFICIENT_DATA"
]


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    reasons: list[str]


def classify_regime(features: MarketFeatures, candle_count: int) -> RegimeResult:
    """Precedence order (first matching rule wins — see
    docs/technical-analysis.md for the full decision table):

    1. INSUFFICIENT_DATA — fewer than MIN_CANDLES_FOR_FEATURES candles,
       or the trend alignment score itself couldn't be computed.
    2. HIGH_VOLATILITY — volatility_state is "elevated" (checked before
       trend, since an elevated-volatility market deserves the warning
       regardless of trend direction).
    3. LOW_VOLATILITY — volatility_state is "low" and trend alignment is
       weak (a quiet, directionless market).
    4. BULLISH — trend direction is bullish with at least partial
       alignment, and volatility isn't elevated.
    5. BEARISH — the bearish mirror of rule 4.
    6. SIDEWAYS — everything else (the default/fallback).
    """
    if candle_count < MIN_CANDLES_FOR_FEATURES or features.trend_alignment_score is None:
        return RegimeResult(
            regime="INSUFFICIENT_DATA",
            reasons=[
                f"fewer than {MIN_CANDLES_FOR_FEATURES} candles available "
                f"({candle_count}) or trend indicators not yet computable"
            ],
        )

    if features.volatility_state == "elevated":
        return RegimeResult(
            regime="HIGH_VOLATILITY",
            reasons=["ATR is elevated relative to price (volatility_state=elevated)"],
        )

    if features.volatility_state == "low" and features.trend_alignment_score == 0:
        return RegimeResult(
            regime="LOW_VOLATILITY",
            reasons=[
                "ATR is low relative to price (volatility_state=low)",
                "trend checks show no consistent direction (trend_alignment_score=0)",
            ],
        )

    if features.trend_direction == "bullish" and features.trend_alignment_score >= 1:
        return RegimeResult(
            regime="BULLISH",
            reasons=[f"trend checks lean bullish with {features.trend_alignment_label} alignment"],
        )

    if features.trend_direction == "bearish" and features.trend_alignment_score >= 1:
        return RegimeResult(
            regime="BEARISH",
            reasons=[f"trend checks lean bearish with {features.trend_alignment_label} alignment"],
        )

    return RegimeResult(
        regime="SIDEWAYS",
        reasons=["no dominant trend direction and volatility is within its normal range"],
    )
