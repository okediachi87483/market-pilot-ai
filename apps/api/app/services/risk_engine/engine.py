"""RiskEngine — the deterministic core of Phase 6 (Step 2).

Turns a `SignalCandidate`-shaped request plus the active policy and
current portfolio state into a `RiskEvaluationOutcome`: APPROVED or
REJECTED, with a complete, named, ordered check trail (Step 5/6) and an
engine-computed position size/stop-loss/take-profit (Step 7/9/10) —
never taken from the signal or any future AI suggestion.

Independent of FastAPI and the database, exactly like
`app/services/signal_engine/engine.py`: this module takes plain
dataclasses in (`RiskEvaluationRequest`, `RiskPolicySnapshot`,
`PortfolioSnapshot`, an already-fetched `entry_price`) and returns a
plain dataclass out. `RiskService` is the only piece that knows about
the database, `MarketDataService`, or the `Signal`/`RiskPolicy` ORM
models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.services.risk_engine import checks as checks_module
from app.services.risk_engine import sizing
from app.services.risk_engine.types import (
    PortfolioSnapshot,
    RiskDecision,
    RiskEvaluationOutcome,
    RiskPolicySnapshot,
)
from app.services.signal_engine.risk_boundary import RiskEvaluationRequest


class RiskEngine:
    """Stateless — `evaluate` is a pure function of its input (Step 26:
    "identical input produces identical output"). No network calls, no
    database access, no randomness."""

    def evaluate(
        self,
        request: RiskEvaluationRequest,
        *,
        policy: RiskPolicySnapshot,
        portfolio: PortfolioSnapshot,
        entry_price: Decimal,
        now: datetime,
    ) -> RiskEvaluationOutcome:
        stop_loss_price: Decimal | None = None
        take_profit_price: Decimal | None = None
        quantity = Decimal("0")
        position_value = Decimal("0")

        # Stop-loss/take-profit/sizing are pure arithmetic on the policy's
        # configured percentages and the current entry price — computed
        # once, up front, so checks 7/8 (which need a quantity) and
        # checks 9/10 (which validate the very same prices) both see
        # identical numbers. Only meaningful for an actionable BUY with a
        # positive entry price; anything else leaves these at their safe
        # zero/None defaults and check 1 (or 9/10) reports why.
        if request.signal == "BUY" and entry_price > 0:
            stop_loss_price = sizing.compute_stop_loss_price(entry_price, policy)
            take_profit_price = sizing.compute_take_profit_price(entry_price, policy)
            quantity = sizing.compute_position_size(
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                policy=policy,
                portfolio=portfolio,
            )
            position_value = quantity * entry_price

        check_results = checks_module.evaluate_checks(
            request=request,
            policy=policy,
            portfolio=portfolio,
            entry_price=entry_price if entry_price > 0 else None,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            quantity=quantity,
            position_value=position_value,
            now=now,
        )

        decision: RiskDecision = "APPROVED" if all(c.passed for c in check_results) else "REJECTED"
        reasons = [c.detail for c in check_results if not c.passed and not c.skipped]

        # Computed numbers are preserved on the outcome regardless of
        # decision (Step 18 auditability: "a future reviewer should be
        # able to answer why Risk Engine approved OR rejected this
        # trade" — that includes seeing what the size/stop/target *would
        # have been* for a rejected candidate, not just for an approved
        # one). The Signal Center UI (Step 22) is what chooses to hide
        # these for a rejected candidate, not this layer.
        return RiskEvaluationOutcome(
            decision=decision,
            checks=check_results,
            reasons=reasons,
            calculated_position_size=quantity,
            entry_price=entry_price if entry_price > 0 else None,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            position_value=position_value,
            policy_id=policy.id,
            policy_version=policy.version,
            portfolio_snapshot=portfolio,
            evaluated_at=now,
        )
