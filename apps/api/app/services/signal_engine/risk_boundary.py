"""The interface boundary between the Signal Engine and the Risk Engine
(Step 16, docs/signal-engine.md §11). Phase 5 defined this shape before
anything consumed it; Phase 6's `RiskEngine`
(app/services/risk_engine/) is that consumer.

The Signal Engine must never bypass this boundary: a `SignalCandidate`
(status always "CANDIDATE") is data, not an instruction. Only the
`RiskEngine`/`RiskService` may change a signal's status to
RISK_APPROVED or RISK_REJECTED — see docs/risk-engine.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.signal import Signal
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
    """Builds the request from an in-process `SignalCandidate` (before
    persistence). Not currently called by any runtime path — `RiskService`
    always evaluates an already-persisted `Signal` row, via
    `to_risk_evaluation_request_from_signal` below — but kept as the
    Phase 5-authored proof that the boundary's shape matches a real
    `SignalCandidate`, independent of the database."""
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


def to_risk_evaluation_request_from_signal(signal: Signal) -> RiskEvaluationRequest:
    """Builds the request from a persisted `Signal` row — what
    `RiskService.evaluate_signal()` actually calls. Requires `signal.asset`
    to already be loaded (the model's `asset` relationship is
    `lazy="joined"`, so a normal query already has it)."""
    return RiskEvaluationRequest(
        signal_id=signal.id,
        symbol=signal.asset.symbol,
        signal=signal.signal,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        strength=signal.strength,
        reasons=signal.reasons,
        supporting_features=signal.supporting_features,
        invalidating_conditions=signal.invalidating_conditions,
    )
