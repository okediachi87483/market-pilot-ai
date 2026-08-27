"""Deterministic, fully-explainable signal strength scoring (Step 7).

No fabricated probability anywhere in this module — "STRONG" never means
"87% chance of winning," it means "four independent, documented
components all scored at or near their maximum." Every point is derived
from a value already computed by Phase 4 (docs/technical-analysis.md);
nothing here is a new indicator.

Only called for BUY/SELL outcomes (rules.py already gates HOLD before
scoring is relevant — see docs/signal-engine.md §"Strength calculation").
"""

from __future__ import annotations

from app.services.signal_engine.types import SignalInput, SignalStrength


def component_scores(signal_input: SignalInput) -> dict[str, int]:
    """Four components, each 0-2. Because scoring only runs for BUY/SELL
    (rules.py already required regime BULLISH/BEARISH with MACD
    confirmation, non-extreme RSI, and non-low volume to reach here), the
    achievable range for each component is narrower than 0-2 in practice
    — see the table in docs/signal-engine.md."""
    features = signal_input.features

    # trend: direct reuse of Phase 4's own 0/1/2 trend_alignment_score.
    # Reaching BUY/SELL already requires alignment >= 1 (docs/technical-analysis.md
    # §7 rules 4-5), so this is 1 or 2 here, never 0.
    trend = features.trend_alignment_score or 0

    # momentum: RSI centrality. "neutral" is the healthiest read; a
    # stretched-but-not-extreme reading (overbought or oversold — the
    # extreme end already blocked by rules.py) scores lower. This is
    # symmetric by design: an oversold RSI during a BULLISH+MACD-bullish
    # setup is a reversal read (still meaningful, scored 1), and the
    # mirror holds for an overbought RSI during a BEARISH+MACD-bearish
    # setup.
    momentum = 2 if features.rsi_state == "neutral" else 1

    # volume: "low" is already excluded by rules.py before scoring runs.
    volume = 2 if features.volume_state == "elevated" else 1

    # volatility: "elevated" is structurally excluded by the regime gate
    # (see rules.py's note on rule 3) before scoring runs.
    volatility = 2 if features.volatility_state == "normal" else 1

    return {
        "trend": trend,
        "momentum": momentum,
        "volume": volume,
        "volatility": volatility,
    }


def strength_from_scores(scores: dict[str, int]) -> SignalStrength:
    """Sum of the four components (range 4-8 in practice, since BUY/SELL
    can only be reached with every component >= 1 — see component_scores)
    mapped to a three-level label. Documented boundaries, not tuned
    against any historical data:

    | total | strength |
    |-------|----------|
    | <= 4  | WEAK     |
    | 5-6   | MODERATE |
    | >= 7  | STRONG   |
    """
    total = sum(scores.values())
    if total <= 4:
        return "WEAK"
    if total <= 6:
        return "MODERATE"
    return "STRONG"
