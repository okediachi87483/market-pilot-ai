"""Shared types for the Paper Trading Engine — kept in their own module
so `engine.py`, `pricing.py`, and `execution.py` can all depend on them
without a circular import, mirroring `signal_engine`/`risk_engine`'s own
`types.py`.

Nothing here imports FastAPI, SQLAlchemy, or the database (Step 2): the
engine operates on plain dataclasses in, plain dataclasses out.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

OrderSide = Literal["BUY", "SELL"]
OrderStatus = Literal["PENDING", "FILLED", "REJECTED", "CANCELLED"]
PositionStatus = Literal["OPEN", "CLOSED"]


class InsufficientPositionError(Exception):
    """Raised by `PaperTradingEngine.apply_sell_fill` when there is no
    open position to sell from, or the requested quantity exceeds what's
    held (Step 10/11: never create a negative/short quantity). A plain
    Python exception — the engine stays independent of `app.core.errors`
    (which is an HTTP-envelope concept); `PaperTradingService` is what
    translates this into a `ConflictError`."""


@dataclass(frozen=True)
class PositionSnapshot:
    """The minimal shape `PaperTradingEngine` needs to know about an
    existing position — not the ORM row."""

    quantity: Decimal
    avg_entry_price: Decimal


@dataclass(frozen=True)
class FillCalculation:
    """What `ExecutionAdapter.fill()` (execution.py) produces — the
    result of simulating one market order fill (Step 6/7)."""

    price: Decimal
    fee: Decimal
    notional: Decimal  # quantity * price, before fee


@dataclass(frozen=True)
class PositionUpdateResult:
    """What applying one fill to a position produces (Step 9/10) —
    everything `PaperTradingService` needs to persist the resulting
    `PaperPosition` row. `realized_pnl_delta` is `0` for a BUY (opening
    or adding never realizes anything); for a SELL it's this fill's
    contribution, computed once and never re-derived later."""

    new_quantity: Decimal
    new_avg_entry_price: Decimal
    realized_pnl_delta: Decimal
    status: PositionStatus
