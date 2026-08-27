"""SignalEngine — the deterministic core of Phase 5.

Turns Phase 4's technical-analysis output (regime + features) into a
structured trade *candidate*: BUY, SELL, or HOLD, with full reasoning.
No AI, no execution, no broker access anywhere in this module or its
package (Step 15/21). See docs/signal-engine.md for the full rule set.

Independent of FastAPI, the database, and TechnicalAnalysisService's own
internals — it depends only on the small `SignalInput` shape in types.py,
so it can be unit-tested with hand-built inputs and reused without a live
database (Step 2, mirroring technical_analysis's independence).
"""

from __future__ import annotations

from app.services.signal_engine import rules, scoring
from app.services.signal_engine.types import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    SignalCandidate,
    SignalInput,
    SignalStrength,
)


class SignalEngine:
    """Stateless — `evaluate` is a pure function of its input. No network
    calls, no database access, no randomness: the same `SignalInput`
    always produces the same `SignalCandidate` (Step 17/18)."""

    def evaluate(self, signal_input: SignalInput) -> SignalCandidate:
        outcome = rules.evaluate_rules(signal_input)

        strength: SignalStrength | None = None
        score_breakdown: dict[str, int] = {}
        if outcome.signal in ("BUY", "SELL"):
            score_breakdown = scoring.component_scores(signal_input)
            strength = scoring.strength_from_scores(score_breakdown)

        supporting_features: dict[str, object] = {
            "trend_alignment_score": signal_input.features.trend_alignment_score,
            "trend_alignment_label": signal_input.features.trend_alignment_label,
            "trend_direction": signal_input.features.trend_direction,
            "rsi14": signal_input.rsi14,
            "rsi_state": signal_input.features.rsi_state,
            "macd_state": signal_input.features.macd_state,
            "volume_state": signal_input.features.volume_state,
            "volatility_state": signal_input.features.volatility_state,
            "regime": signal_input.regime.regime,
        }

        return SignalCandidate(
            symbol=signal_input.symbol,
            signal=outcome.signal,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            timestamp=signal_input.timestamp,
            reasons=outcome.reasons,
            supporting_features=supporting_features,
            invalidating_conditions=outcome.invalidating_conditions,
            market_regime=signal_input.regime.regime,
            strength=strength,
            score_breakdown=score_breakdown,
        )
