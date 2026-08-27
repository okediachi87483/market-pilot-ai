"""Unit tests for app/services/risk_engine/sizing.py — stop-loss,
take-profit, and position-size calculation (Steps 7/8/9/10). Pure
functions, no database."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.risk_engine.sizing import (
    compute_position_size,
    compute_stop_loss_price,
    compute_take_profit_price,
)
from app.services.risk_engine.types import PortfolioSnapshot, RiskPolicySnapshot


def _policy(**overrides) -> RiskPolicySnapshot:
    fields = dict(
        id=uuid.uuid4(),
        name="default",
        version=1,
        enabled=True,
        max_position_size_pct=Decimal("5.00"),
        max_portfolio_exposure_pct=Decimal("50.00"),
        max_daily_loss_pct=Decimal("3.00"),
        max_drawdown_pct=Decimal("15.00"),
        stop_loss_pct=Decimal("2.00"),
        take_profit_pct=Decimal("4.00"),
        max_concurrent_positions=5,
        cooldown_after_loss_minutes=60,
        risk_per_trade_pct=Decimal("1.00"),
    )
    fields.update(overrides)
    return RiskPolicySnapshot(**fields)


def _portfolio(**overrides) -> PortfolioSnapshot:
    fields = dict(
        equity=Decimal("100000"),
        cash=Decimal("100000"),
        high_water_mark=Decimal("100000"),
        open_position_count=0,
        open_position_value=Decimal("0"),
        realized_pl_today=Decimal("0"),
        last_losing_trade_at=None,
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )
    fields.update(overrides)
    return PortfolioSnapshot(**fields)


# --- stop-loss / take-profit -------------------------------------------


def test_stop_loss_is_below_entry_by_configured_percent():
    policy = _policy(stop_loss_pct=Decimal("2.00"))
    stop = compute_stop_loss_price(Decimal("100.00"), policy)
    assert stop == Decimal("98.00000000")
    assert stop < Decimal("100.00")


def test_take_profit_is_above_entry_by_configured_percent():
    policy = _policy(take_profit_pct=Decimal("4.00"))
    target = compute_take_profit_price(Decimal("100.00"), policy)
    assert target == Decimal("104.00000000")
    assert target > Decimal("100.00")


def test_stop_loss_and_take_profit_are_deterministic():
    policy = _policy()
    first = compute_stop_loss_price(Decimal("173.45"), policy)
    second = compute_stop_loss_price(Decimal("173.45"), policy)
    assert first == second


def test_stop_loss_scales_with_entry_price():
    policy = _policy(stop_loss_pct=Decimal("10.00"))
    stop = compute_stop_loss_price(Decimal("50.00"), policy)
    assert stop == Decimal("45.00000000")


# --- position sizing -----------------------------------------------------


def test_position_size_uses_risk_budget_over_risk_per_unit():
    # equity=100000, risk_per_trade=1% -> risk_budget=1000
    # entry=100, stop=98 -> risk_per_unit=2 -> raw_quantity=500
    # max_qty_by_position_size = (100000*5%)/100 = 50
    # so the hard position-size cap binds, not the raw risk-based quantity.
    policy = _policy()
    portfolio = _portfolio()
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    assert quantity == Decimal("50.0000000000")


def test_position_size_is_constrained_by_max_position_size_pct():
    policy = _policy(max_position_size_pct=Decimal("1.00"), risk_per_trade_pct=Decimal("100.00"))
    portfolio = _portfolio()
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    max_position_value = portfolio.equity * policy.max_position_size_pct / Decimal("100")
    assert quantity * entry <= max_position_value


def test_position_size_is_constrained_by_exposure_headroom():
    policy = _policy(
        max_portfolio_exposure_pct=Decimal("10.00"), risk_per_trade_pct=Decimal("100.00")
    )
    # Already 9% of equity exposed -> only 1% of headroom left.
    portfolio = _portfolio(open_position_value=Decimal("9000"))
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    assert quantity * entry <= Decimal("1000.01")  # ~1% of 100000 headroom


def test_position_size_is_zero_when_no_exposure_headroom_remains():
    policy = _policy(max_portfolio_exposure_pct=Decimal("10.00"))
    portfolio = _portfolio(open_position_value=Decimal("10000"))  # already at the cap
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    assert quantity == Decimal("0")


def test_position_size_is_constrained_by_available_cash():
    policy = _policy(risk_per_trade_pct=Decimal("100.00"), max_position_size_pct=Decimal("100.00"))
    portfolio = _portfolio(equity=Decimal("100000"), cash=Decimal("500"))
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    assert quantity * entry <= Decimal("500")


def test_position_size_is_zero_for_non_positive_entry_price():
    policy = _policy()
    portfolio = _portfolio()
    quantity = compute_position_size(
        entry_price=Decimal("0"),
        stop_loss_price=Decimal("0"),
        policy=policy,
        portfolio=portfolio,
    )
    assert quantity == Decimal("0")


def test_position_size_is_zero_for_negative_entry_price():
    policy = _policy()
    portfolio = _portfolio()
    quantity = compute_position_size(
        entry_price=Decimal("-10"),
        stop_loss_price=Decimal("-12"),
        policy=policy,
        portfolio=portfolio,
    )
    assert quantity == Decimal("0")


def test_position_size_is_zero_for_zero_stop_distance():
    # stop == entry -> risk_per_unit == 0 -> must never divide by zero.
    policy = _policy()
    portfolio = _portfolio()
    quantity = compute_position_size(
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("100.00"),
        policy=policy,
        portfolio=portfolio,
    )
    assert quantity == Decimal("0")


def test_position_size_is_zero_for_inverted_stop_distance():
    # stop above entry (would be a negative risk_per_unit) is never sized.
    policy = _policy()
    portfolio = _portfolio()
    quantity = compute_position_size(
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("110.00"),
        policy=policy,
        portfolio=portfolio,
    )
    assert quantity == Decimal("0")


def test_position_size_is_zero_for_non_positive_equity():
    policy = _policy()
    portfolio = _portfolio(equity=Decimal("0"), cash=Decimal("0"))
    quantity = compute_position_size(
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("98.00"),
        policy=policy,
        portfolio=portfolio,
    )
    assert quantity == Decimal("0")


def test_position_size_never_rounds_up():
    # A quantity that would round up under normal rounding must instead
    # round down, so the computed position never exceeds its constraint.
    policy = _policy(max_position_size_pct=Decimal("5.00"), risk_per_trade_pct=Decimal("100.00"))
    portfolio = _portfolio(equity=Decimal("333.33"), cash=Decimal("333.33"))
    entry = Decimal("100.00")
    stop = compute_stop_loss_price(entry, policy)

    quantity = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )

    max_position_value = portfolio.equity * policy.max_position_size_pct / Decimal("100")
    assert quantity * entry <= max_position_value


def test_position_size_is_deterministic():
    policy = _policy()
    portfolio = _portfolio()
    entry = Decimal("173.45")
    stop = compute_stop_loss_price(entry, policy)

    first = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )
    second = compute_position_size(
        entry_price=entry, stop_loss_price=stop, policy=policy, portfolio=portfolio
    )
    assert first == second
