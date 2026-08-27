"""Unit tests for app/services/paper_trading/engine.py —
`PaperTradingEngine.apply_buy_fill`/`apply_sell_fill` (Steps 9/10/11).
Pure functions, no database."""

from decimal import Decimal

import pytest

from app.services.paper_trading.engine import PaperTradingEngine
from app.services.paper_trading.types import InsufficientPositionError, PositionSnapshot

engine = PaperTradingEngine()


# --- apply_buy_fill (Step 9) ----------------------------------------------


def test_buy_fill_opens_a_new_position_when_none_exists():
    result = engine.apply_buy_fill(None, Decimal("10"), Decimal("100.00"))
    assert result.new_quantity == Decimal("10")
    assert result.new_avg_entry_price == Decimal("100.00")
    assert result.realized_pnl_delta == Decimal("0")
    assert result.status == "OPEN"


def test_buy_fill_increases_an_existing_position_with_weighted_average():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    result = engine.apply_buy_fill(existing, Decimal("10"), Decimal("120.00"))
    assert result.new_quantity == Decimal("20")
    assert result.new_avg_entry_price == Decimal("110.00")
    assert result.realized_pnl_delta == Decimal("0")
    assert result.status == "OPEN"


def test_buy_fill_never_realizes_pnl():
    existing = PositionSnapshot(quantity=Decimal("5"), avg_entry_price=Decimal("50.00"))
    result = engine.apply_buy_fill(
        existing, Decimal("5"), Decimal("40.00")
    )  # buying "at a loss" vs avg
    assert result.realized_pnl_delta == Decimal("0")


def test_buy_fill_is_deterministic():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    first = engine.apply_buy_fill(existing, Decimal("5"), Decimal("105.00"))
    second = engine.apply_buy_fill(existing, Decimal("5"), Decimal("105.00"))
    assert first == second


# --- apply_sell_fill (Step 10) --------------------------------------------


def test_sell_fill_partial_reduces_the_position_and_keeps_it_open():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    result = engine.apply_sell_fill(existing, Decimal("4"), Decimal("110.00"), Decimal("1.00"))
    assert result.new_quantity == Decimal("6")
    assert result.new_avg_entry_price == Decimal("100.00")  # unchanged on a partial close
    assert result.realized_pnl_delta == Decimal("39.00")  # (110-100)*4 - 1
    assert result.status == "OPEN"


def test_sell_fill_full_close_zeroes_the_position():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    result = engine.apply_sell_fill(existing, Decimal("10"), Decimal("90.00"), Decimal("1.00"))
    assert result.new_quantity == Decimal("0")
    assert result.status == "CLOSED"
    assert result.realized_pnl_delta == Decimal("-101.00")  # (90-100)*10 - 1


def test_sell_fill_sequence_of_partial_closes_each_realize_independently():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    first = engine.apply_sell_fill(existing, Decimal("3"), Decimal("110.00"), Decimal("0"))
    remaining = PositionSnapshot(
        quantity=first.new_quantity, avg_entry_price=first.new_avg_entry_price
    )
    second = engine.apply_sell_fill(remaining, Decimal("7"), Decimal("120.00"), Decimal("0"))

    assert first.realized_pnl_delta == Decimal("30.00")  # (110-100)*3
    assert second.realized_pnl_delta == Decimal("140.00")  # (120-100)*7
    assert second.new_quantity == Decimal("0")
    assert second.status == "CLOSED"


# --- Step 11: no shorting, never a negative quantity ----------------------


def test_sell_fill_with_no_existing_position_raises():
    with pytest.raises(InsufficientPositionError, match="No long position exists for SELL"):
        engine.apply_sell_fill(None, Decimal("1"), Decimal("100.00"), Decimal("0"))


def test_sell_fill_with_zero_quantity_position_raises():
    existing = PositionSnapshot(quantity=Decimal("0"), avg_entry_price=Decimal("100.00"))
    with pytest.raises(InsufficientPositionError):
        engine.apply_sell_fill(existing, Decimal("1"), Decimal("100.00"), Decimal("0"))


def test_sell_fill_exceeding_held_quantity_raises_and_never_goes_negative():
    existing = PositionSnapshot(quantity=Decimal("5"), avg_entry_price=Decimal("100.00"))
    with pytest.raises(InsufficientPositionError):
        engine.apply_sell_fill(existing, Decimal("6"), Decimal("100.00"), Decimal("0"))


def test_sell_fill_exactly_at_held_quantity_succeeds():
    existing = PositionSnapshot(quantity=Decimal("5"), avg_entry_price=Decimal("100.00"))
    result = engine.apply_sell_fill(existing, Decimal("5"), Decimal("100.00"), Decimal("0"))
    assert result.new_quantity == Decimal("0")
    assert result.status == "CLOSED"


def test_sell_fill_is_deterministic():
    existing = PositionSnapshot(quantity=Decimal("10"), avg_entry_price=Decimal("100.00"))
    first = engine.apply_sell_fill(existing, Decimal("5"), Decimal("105.00"), Decimal("1.00"))
    second = engine.apply_sell_fill(existing, Decimal("5"), Decimal("105.00"), Decimal("1.00"))
    assert first == second
