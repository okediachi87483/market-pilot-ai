"""Unit tests for app/services/paper_trading/pricing.py — fee, weighted
average entry, realized/unrealized P/L (Steps 6/7/9/10/12). Pure
functions, no database."""

from decimal import Decimal

from app.services.paper_trading.pricing import (
    compute_fee,
    compute_notional,
    compute_realized_pnl,
    compute_unrealized_pnl,
    compute_weighted_average_entry,
)


def test_notional_is_quantity_times_price():
    assert compute_notional(Decimal("10"), Decimal("100.00")) == Decimal("1000.00")


def test_fee_is_notional_times_rate():
    fee = compute_fee(Decimal("1000.00"), Decimal("0.001"))
    assert fee == Decimal("1.00000000")


def test_fee_is_zero_for_zero_rate():
    fee = compute_fee(Decimal("1000.00"), Decimal("0"))
    assert fee == Decimal("0")


def test_fee_is_deterministic():
    first = compute_fee(Decimal("1234.56"), Decimal("0.001"))
    second = compute_fee(Decimal("1234.56"), Decimal("0.001"))
    assert first == second


# --- weighted average entry (Step 9) -----------------------------------


def test_weighted_average_entry_for_a_new_position_is_the_fill_price():
    avg = compute_weighted_average_entry(
        Decimal("0"), Decimal("0"), Decimal("10"), Decimal("100.00")
    )
    assert avg == Decimal("100.00")


def test_weighted_average_entry_for_adding_to_a_position():
    # 10 @ 100 + 10 @ 120 -> 20 @ 110
    avg = compute_weighted_average_entry(
        Decimal("10"), Decimal("100.00"), Decimal("10"), Decimal("120.00")
    )
    assert avg == Decimal("110.00")


def test_weighted_average_entry_with_uneven_quantities():
    # 10 @ 100 + 30 @ 200 -> 40 @ 175
    avg = compute_weighted_average_entry(
        Decimal("10"), Decimal("100.00"), Decimal("30"), Decimal("200.00")
    )
    assert avg == Decimal("175.00")


def test_weighted_average_entry_is_deterministic():
    first = compute_weighted_average_entry(
        Decimal("5"), Decimal("50.00"), Decimal("5"), Decimal("60.00")
    )
    second = compute_weighted_average_entry(
        Decimal("5"), Decimal("50.00"), Decimal("5"), Decimal("60.00")
    )
    assert first == second


# --- realized P/L (Step 10) ---------------------------------------------


def test_realized_pnl_is_positive_for_a_profitable_close():
    pnl = compute_realized_pnl(Decimal("100.00"), Decimal("110.00"), Decimal("10"), Decimal("1.00"))
    assert pnl == Decimal("99.00")  # (110-100)*10 - 1


def test_realized_pnl_is_negative_for_a_loss():
    pnl = compute_realized_pnl(Decimal("100.00"), Decimal("90.00"), Decimal("10"), Decimal("1.00"))
    assert pnl == Decimal("-101.00")  # (90-100)*10 - 1


def test_realized_pnl_is_zero_at_breakeven_before_fees():
    pnl = compute_realized_pnl(Decimal("100.00"), Decimal("100.00"), Decimal("10"), Decimal("0"))
    assert pnl == Decimal("0.00")


def test_realized_pnl_fees_always_reduce_the_result():
    no_fee = compute_realized_pnl(Decimal("100.00"), Decimal("110.00"), Decimal("10"), Decimal("0"))
    with_fee = compute_realized_pnl(
        Decimal("100.00"), Decimal("110.00"), Decimal("10"), Decimal("5.00")
    )
    assert with_fee == no_fee - Decimal("5.00")


# --- unrealized P/L (Step 12) --------------------------------------------


def test_unrealized_pnl_is_positive_when_price_is_above_entry():
    pnl = compute_unrealized_pnl(Decimal("100.00"), Decimal("110.00"), Decimal("10"))
    assert pnl == Decimal("100.00")


def test_unrealized_pnl_is_negative_when_price_is_below_entry():
    pnl = compute_unrealized_pnl(Decimal("100.00"), Decimal("90.00"), Decimal("10"))
    assert pnl == Decimal("-100.00")


def test_unrealized_pnl_has_no_fee_term():
    # Unlike realized P/L, unrealized P/L takes no fee argument at all —
    # this test exists to document that omission is deliberate (Step 12).
    pnl = compute_unrealized_pnl(Decimal("100.00"), Decimal("100.00"), Decimal("10"))
    assert pnl == Decimal("0.00")
