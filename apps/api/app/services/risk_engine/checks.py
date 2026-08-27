"""The 11-check risk pipeline (Step 6), in the exact documented
precedence order. Pure function of its inputs — no I/O, no randomness.

Precedence and skip semantics (docs/risk-engine.md §"Check pipeline"
has the full table): checks 1 and 3 are hard gates — if either fails,
every later check is marked `skipped` rather than evaluated, because
nothing downstream is meaningful without an actionable signal (check 1)
or an enabled policy to evaluate against (check 3). Every other check
(4-11) always runs and is reported independently once gating passes, so
a rejection always shows the *complete* risk picture in one response
(Step 6's explicit preference) rather than one failure at a time across
repeated calls. Check 2 ("signal status") is always reported as passed
here — `RiskService` verifies the signal is `CANDIDATE` *before* ever
calling the engine (so an already-decided signal is never silently
re-evaluated, Step 17), so by the time this pipeline runs that
precondition is already guaranteed; it still appears in the audit trail
as an explicit, named, passed check rather than being silently omitted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.services.risk_engine.types import PortfolioSnapshot, RiskCheckResult, RiskPolicySnapshot
from app.services.signal_engine.risk_boundary import RiskEvaluationRequest

HUNDRED = Decimal("100")


def evaluate_checks(
    *,
    request: RiskEvaluationRequest,
    policy: RiskPolicySnapshot,
    portfolio: PortfolioSnapshot,
    entry_price: Decimal | None,
    stop_loss_price: Decimal | None,
    take_profit_price: Decimal | None,
    quantity: Decimal,
    position_value: Decimal,
    now: datetime,
) -> list[RiskCheckResult]:
    checks: list[RiskCheckResult] = []

    # 1. Signal validity — only a BUY candidate is an actionable entry in
    # this phase (Step 9: long-only; no short-position logic). A HOLD
    # carries no direction; a SELL is an exit/reduce suggestion for a
    # position that may exist, but there is no position tracking yet
    # (Phase 7) for the engine to size an exit against.
    if request.signal == "BUY":
        checks.append(
            RiskCheckResult("signal_validity", True, "Signal is an actionable BUY candidate")
        )
    else:
        checks.append(
            RiskCheckResult(
                "signal_validity",
                False,
                f"Signal type {request.signal!r} is not an actionable long-entry candidate "
                "in this phase (only BUY signals are sized) — SELL/HOLD carry no new-entry "
                "action for the Risk Engine to evaluate",
            )
        )
        return checks + _skip_remaining(1)

    # 2. Signal status — precondition already enforced by RiskService
    # before this pipeline is ever invoked (see module docstring).
    checks.append(
        RiskCheckResult("signal_status", True, "Signal status was CANDIDATE at evaluation time")
    )

    # 3. Risk policy enabled — a hard gate: nothing below is meaningful
    # against a paused policy.
    if policy.enabled:
        checks.append(
            RiskCheckResult(
                "risk_policy_enabled", True, f"Active policy {policy.name!r} is enabled"
            )
        )
    else:
        checks.append(
            RiskCheckResult(
                "risk_policy_enabled",
                False,
                f"Active policy {policy.name!r} is currently disabled — no new approvals "
                "while risk evaluation is paused",
            )
        )
        return checks + _skip_remaining(3)

    # 4. Daily loss limit.
    daily_loss_floor = -(portfolio.equity * policy.max_daily_loss_pct / HUNDRED)
    if portfolio.realized_pl_today > daily_loss_floor:
        checks.append(
            RiskCheckResult(
                "daily_loss_limit",
                True,
                f"Realized P/L today ({portfolio.realized_pl_today}) is within the "
                f"{policy.max_daily_loss_pct}% daily loss limit",
            )
        )
    else:
        checks.append(
            RiskCheckResult(
                "daily_loss_limit",
                False,
                f"Realized P/L today ({portfolio.realized_pl_today}) has reached the "
                f"{policy.max_daily_loss_pct}% daily loss limit ({daily_loss_floor}) — "
                "no new positions for the rest of the trading day",
            )
        )

    # 5. Maximum drawdown. A non-positive high-water mark is an invalid
    # portfolio state (Step 15: "handle peak_equity <= 0 safely, never
    # divide by zero") — fail closed rather than compute a meaningless
    # ratio.
    if portfolio.high_water_mark <= 0:
        checks.append(
            RiskCheckResult(
                "max_drawdown",
                False,
                "Portfolio high-water mark is non-positive — invalid portfolio state, "
                "failing closed",
            )
        )
    else:
        drawdown_pct = (
            (portfolio.high_water_mark - portfolio.equity) / portfolio.high_water_mark * HUNDRED
        )
        if drawdown_pct < policy.max_drawdown_pct:
            checks.append(
                RiskCheckResult(
                    "max_drawdown",
                    True,
                    f"Drawdown ({drawdown_pct:.2f}%) is within the "
                    f"{policy.max_drawdown_pct}% limit",
                )
            )
        else:
            checks.append(
                RiskCheckResult(
                    "max_drawdown",
                    False,
                    f"Drawdown ({drawdown_pct:.2f}%) has reached the "
                    f"{policy.max_drawdown_pct}% limit — no new positions until it recovers",
                )
            )

    # 6. Maximum concurrent positions.
    proposed_count = portfolio.open_position_count + 1
    if proposed_count <= policy.max_concurrent_positions:
        checks.append(
            RiskCheckResult(
                "max_concurrent_positions",
                True,
                f"{portfolio.open_position_count} open position(s); this candidate would make "
                f"{proposed_count}, within the limit of {policy.max_concurrent_positions}",
            )
        )
    else:
        checks.append(
            RiskCheckResult(
                "max_concurrent_positions",
                False,
                f"{portfolio.open_position_count} open position(s) already at/above the limit "
                f"of {policy.max_concurrent_positions}",
            )
        )

    # 7. Portfolio exposure.
    max_exposure_value = portfolio.equity * policy.max_portfolio_exposure_pct / HUNDRED
    proposed_exposure = portfolio.open_position_value + position_value
    if proposed_exposure <= max_exposure_value:
        checks.append(
            RiskCheckResult(
                "portfolio_exposure",
                True,
                f"Proposed exposure ({proposed_exposure}) is within the "
                f"{policy.max_portfolio_exposure_pct}% limit ({max_exposure_value})",
            )
        )
    else:
        checks.append(
            RiskCheckResult(
                "portfolio_exposure",
                False,
                f"Proposed exposure ({proposed_exposure}) would exceed the "
                f"{policy.max_portfolio_exposure_pct}% limit ({max_exposure_value})",
            )
        )

    # 8. Position-size limit.
    max_position_value = portfolio.equity * policy.max_position_size_pct / HUNDRED
    if quantity > 0 and position_value <= max_position_value:
        checks.append(
            RiskCheckResult(
                "position_size_limit",
                True,
                f"Calculated position value ({position_value}) is within the "
                f"{policy.max_position_size_pct}% per-position limit ({max_position_value})",
            )
        )
    else:
        checks.append(
            RiskCheckResult(
                "position_size_limit",
                False,
                "No valid position size could be computed within the configured limits"
                if quantity <= 0
                else f"Calculated position value ({position_value}) would exceed the "
                f"{policy.max_position_size_pct}% per-position limit ({max_position_value})",
            )
        )

    # 9. Stop-loss validity.
    if entry_price is not None and entry_price > 0 and stop_loss_price is not None:
        if 0 < stop_loss_price < entry_price:
            checks.append(
                RiskCheckResult(
                    "stop_loss_validity",
                    True,
                    f"Stop-loss ({stop_loss_price}) is valid and below entry ({entry_price})",
                )
            )
        else:
            checks.append(
                RiskCheckResult(
                    "stop_loss_validity",
                    False,
                    f"Computed stop-loss ({stop_loss_price}) is not a valid price below "
                    f"entry ({entry_price})",
                )
            )
    else:
        checks.append(
            RiskCheckResult(
                "stop_loss_validity", False, "Entry price or stop-loss price is missing/invalid"
            )
        )

    # 10. Take-profit validity.
    if entry_price is not None and entry_price > 0 and take_profit_price is not None:
        if take_profit_price > entry_price > 0:
            checks.append(
                RiskCheckResult(
                    "take_profit_validity",
                    True,
                    f"Take-profit ({take_profit_price}) is valid and above entry "
                    f"({entry_price})",
                )
            )
        else:
            checks.append(
                RiskCheckResult(
                    "take_profit_validity",
                    False,
                    f"Computed take-profit ({take_profit_price}) is not a valid price above "
                    f"entry ({entry_price})",
                )
            )
    else:
        checks.append(
            RiskCheckResult(
                "take_profit_validity",
                False,
                "Entry price or take-profit price is missing/invalid",
            )
        )

    # 11. Loss cooldown.
    if portfolio.last_losing_trade_at is None:
        checks.append(RiskCheckResult("loss_cooldown", True, "No recent losing trade on record"))
    else:
        elapsed_minutes = (now - portfolio.last_losing_trade_at).total_seconds() / 60
        if elapsed_minutes >= policy.cooldown_after_loss_minutes:
            checks.append(
                RiskCheckResult(
                    "loss_cooldown",
                    True,
                    f"{elapsed_minutes:.1f} minutes since the last losing trade — past the "
                    f"{policy.cooldown_after_loss_minutes}-minute cooldown",
                )
            )
        else:
            checks.append(
                RiskCheckResult(
                    "loss_cooldown",
                    False,
                    f"Only {elapsed_minutes:.1f} minutes since the last losing trade — inside "
                    f"the {policy.cooldown_after_loss_minutes}-minute cooldown",
                )
            )

    return checks


def _skip_remaining(evaluated_count: int) -> list[RiskCheckResult]:
    from app.services.risk_engine.types import RISK_CHECK_NAMES

    remaining = RISK_CHECK_NAMES[evaluated_count:]
    return [
        RiskCheckResult(name, False, "Not evaluated — an earlier hard-gate check failed", True)
        for name in remaining
    ]
