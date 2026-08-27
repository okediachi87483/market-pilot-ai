"""The interface boundary between the Signal Engine and the future Risk
Engine (Step 16). Nothing in this codebase consumes `RiskEvaluationRequest`
yet — Phase 6 builds the `RiskEngine` that will. This module exists now so
the boundary is a concrete, typed shape from the start, not an
after-the-fact retrofit.

The Signal Engine must never bypass this boundary: a `SignalCandidate`
(status always "CANDIDATE") is data, not an instruction. Only a
(future) RiskEngine may change a signal's status to RISK_APPROVED or
RISK_REJECTED — see docs/signal-engine.md §"Relationship to the Risk
Engine" and docs/risk-engine.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.services.signal_engine.types import SignalCandidate


@dataclass(frozen=True)
class RiskEvaluationRequest:
    """What the future Risk Engine will receive. Deliberately carries the
    full reasoning context (Step 11 auditability), not just the bare
    signal — a risk decision should be traceable to exactly the same
    evidence a human reviewer sees."""

    signal_id: uuid.UUID
    symbol: str
    signal: str  # "BUY" | "SELL"
    strategy_id: str
    strategy_version: str
    strength: str | None
    reasons: list[str]
    supporting_features: dict[str, object]
    invalidating_conditions: list[str]


def to_risk_evaluation_request(
    signal_id: uuid.UUID, candidate: SignalCandidate
) -> RiskEvaluationRequest:
    """Builds the request the Risk Engine will eventually consume. Not
    called anywhere yet — provided so the boundary's shape is validated
    against a real `SignalCandidate` now, rather than only in a future
    phase's tests."""
    return RiskEvaluationRequest(
        signal_id=signal_id,
        symbol=candidate.symbol,
        signal=candidate.signal,
        strategy_id=candidate.strategy_id,
        strategy_version=candidate.strategy_version,
        strength=candidate.strength,
        reasons=candidate.reasons,
        supporting_features=candidate.supporting_features,
        invalidating_conditions=candidate.invalidating_conditions,
    )
