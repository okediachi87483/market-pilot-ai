"""Deterministic fee and P/L arithmetic (Step 6/7/9/10). Pure `Decimal`
functions — no I/O, no randomness. Full formulas and rationale:
docs/paper-trading.md.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

PRICE_PRECISION = Decimal("0.00000001")  # matches PRICE = NUMERIC(20,8)


def compute_notional(quantity: Decimal, price: Decimal) -> Decimal:
    return quantity * price


def compute_fee(notional: Decimal, fee_rate: Decimal) -> Decimal:
    """Step 7: `fee = notional × fee_rate`. Standard half-up rounding —
    unlike position sizing (which always rounds a quantity down to stay
    conservative), a fee is a normal commission calculation with no
    safety bias in either direction."""
    return (notional * fee_rate).quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)


def compute_weighted_average_entry(
    existing_quantity: Decimal,
    existing_avg_price: Decimal,
    add_quantity: Decimal,
    fill_price: Decimal,
) -> Decimal:
    """Step 9: opening or adding to a long position. `existing_quantity
    == 0` (no prior position) collapses to `fill_price` exactly, since
    the weighted-average formula is undefined at zero. Quantized to
    `PRICE_PRECISION` explicitly — `avg_entry_price` is a `NUMERIC(20,8)`
    column, and a raw division can produce far more than 8 fractional
    digits; quantizing here (rather than relying on Postgres to round
    silently on write) keeps the in-process value and the persisted
    value identical, so callers never see one value before a commit and
    a different one after."""
    if existing_quantity <= 0:
        return fill_price.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)
    total_cost = existing_quantity * existing_avg_price + add_quantity * fill_price
    average = total_cost / (existing_quantity + add_quantity)
    return average.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)


def compute_realized_pnl(
    avg_entry_price: Decimal, fill_price: Decimal, quantity: Decimal, fee: Decimal
) -> Decimal:
    """Step 10: `(fill_price - avg_entry_price) × quantity - fee` for a
    long position's reducing/closing SELL. Fees always reduce realized
    P/L (docs/database.md §1: fees are never netted into the fill price
    itself, but they do affect what the account actually keeps).
    Quantized for the same reason as `compute_weighted_average_entry` —
    `paper_fills.realized_pnl` is `NUMERIC(20,8)`."""
    pnl = (fill_price - avg_entry_price) * quantity - fee
    return pnl.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)


def compute_unrealized_pnl(
    avg_entry_price: Decimal, current_price: Decimal, quantity: Decimal
) -> Decimal:
    """Step 12: no fee term — an open position hasn't incurred an exit
    fee yet, so unrealized P/L is deliberately not fee-adjusted (fees
    only ever reduce *realized* P/L, at the moment a sale actually
    happens)."""
    return (current_price - avg_entry_price) * quantity
