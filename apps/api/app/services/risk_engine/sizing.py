"""Deterministic stop-loss, take-profit, and position-size calculation
(Steps 7/9/10). Pure functions of `Decimal` inputs — no I/O, no
randomness, no rounding surprises: quantities are always rounded DOWN,
never up, so a computed position never exceeds what the constraints
actually allow. Full formula and rationale: docs/risk-engine.md
§"Position sizing".
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.services.risk_engine.types import PortfolioSnapshot, RiskPolicySnapshot

QUANTITY_PRECISION = Decimal("0.0000000001")  # matches QUANTITY = NUMERIC(28,10)
PRICE_PRECISION = Decimal("0.00000001")  # matches PRICE = NUMERIC(20,8)

HUNDRED = Decimal("100")


def compute_stop_loss_price(entry_price: Decimal, policy: RiskPolicySnapshot) -> Decimal:
    """Long-only (Step 9): stop sits `stop_loss_pct` below entry. Never
    reads a stop from the signal or any AI suggestion — always
    engine-computed from the active policy, matching docs/risk-engine.md
    §"What the signal/AI may and may not influence"."""
    stop = entry_price * (Decimal(1) - policy.stop_loss_pct / HUNDRED)
    return stop.quantize(PRICE_PRECISION, rounding=ROUND_DOWN)


def compute_take_profit_price(entry_price: Decimal, policy: RiskPolicySnapshot) -> Decimal:
    """Long-only (Step 10): target sits `take_profit_pct` above entry."""
    target = entry_price * (Decimal(1) + policy.take_profit_pct / HUNDRED)
    return target.quantize(PRICE_PRECISION, rounding=ROUND_DOWN)


def compute_position_size(
    *,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    policy: RiskPolicySnapshot,
    portfolio: PortfolioSnapshot,
) -> Decimal:
    """Step 7's formula, implemented exactly as documented in
    docs/risk-engine.md §"Position sizing":

        risk_budget   = equity * risk_per_trade_pct / 100
        risk_per_unit = entry_price - stop_loss_price
        raw_quantity  = risk_budget / risk_per_unit

    ...then constrained (never expanded) by three independent ceilings:
    the hard per-position size cap, the remaining exposure headroom
    under the portfolio-wide exposure cap, and available cash (Step 7's
    "available buying power"). The tightest of the four wins.

    Returns `Decimal("0")` — never raises, never divides by zero — for
    any input that makes sizing meaningless (Step 8): non-positive
    entry/stop, a non-positive stop distance, or non-positive equity.
    The check pipeline (checks.py) is what turns a zero/short quantity
    into a specific, named rejection reason; this function only ever
    answers "how much, if any."
    """
    risk_per_unit = entry_price - stop_loss_price
    if entry_price <= 0 or stop_loss_price <= 0 or risk_per_unit <= 0 or portfolio.equity <= 0:
        return Decimal("0")

    risk_budget = portfolio.equity * policy.risk_per_trade_pct / HUNDRED
    if risk_budget <= 0:
        return Decimal("0")
    raw_quantity = risk_budget / risk_per_unit

    max_position_value = portfolio.equity * policy.max_position_size_pct / HUNDRED
    max_qty_by_position_size = max_position_value / entry_price

    max_exposure_value = portfolio.equity * policy.max_portfolio_exposure_pct / HUNDRED
    remaining_exposure_value = max_exposure_value - portfolio.open_position_value
    max_qty_by_exposure = (
        remaining_exposure_value / entry_price if remaining_exposure_value > 0 else Decimal("0")
    )

    max_qty_by_cash = portfolio.cash / entry_price if portfolio.cash > 0 else Decimal("0")

    quantity = min(raw_quantity, max_qty_by_position_size, max_qty_by_exposure, max_qty_by_cash)
    if quantity <= 0:
        return Decimal("0")
    return quantity.quantize(QUANTITY_PRECISION, rounding=ROUND_DOWN)
