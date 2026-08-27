"""PaperTradingEngine — the deterministic core of Phase 7 (Step 2).

Turns one simulated fill plus the existing position (if any) into a
`PositionUpdateResult`: the new quantity, new average entry price, and
any realized P/L delta. No I/O, no database, no FastAPI — exactly like
`SignalEngine`/`RiskEngine`. `PaperTradingService` is the only piece
that knows about the database or `MarketDataService`.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.paper_trading import pricing
from app.services.paper_trading.types import (
    InsufficientPositionError,
    PositionSnapshot,
    PositionStatus,
    PositionUpdateResult,
)


class PaperTradingEngine:
    """Stateless — both methods are pure functions of their input (the
    same invariant Phase 5/6 already established: identical input
    produces identical output)."""

    def apply_buy_fill(
        self, existing: PositionSnapshot | None, quantity: Decimal, fill_price: Decimal
    ) -> PositionUpdateResult:
        """Step 9: open a new position, or add to an existing one at a
        recomputed weighted-average entry price. A BUY never realizes
        P/L — `realized_pnl_delta` is always `0`."""
        existing_quantity = existing.quantity if existing else Decimal("0")
        existing_avg = existing.avg_entry_price if existing else Decimal("0")

        new_avg = pricing.compute_weighted_average_entry(
            existing_quantity, existing_avg, quantity, fill_price
        )
        return PositionUpdateResult(
            new_quantity=existing_quantity + quantity,
            new_avg_entry_price=new_avg,
            realized_pnl_delta=Decimal("0"),
            status="OPEN",
        )

    def apply_sell_fill(
        self,
        existing: PositionSnapshot | None,
        quantity: Decimal,
        fill_price: Decimal,
        fee: Decimal,
    ) -> PositionUpdateResult:
        """Step 10/11: reduce or close an existing long position.
        Raises `InsufficientPositionError` — never silently creates a
        negative/short quantity — when there is no position, or the
        requested quantity exceeds what's held. Supports a partial
        close (`quantity < existing.quantity` leaves the position
        `OPEN` with an unchanged average entry price — only a BUY ever
        recomputes that average) as well as a full close (`status`
        becomes `CLOSED`)."""
        if existing is None or existing.quantity <= 0:
            raise InsufficientPositionError("No long position exists for SELL.")
        if quantity > existing.quantity:
            raise InsufficientPositionError(
                f"Cannot sell {quantity} — only {existing.quantity} held."
            )

        realized = pricing.compute_realized_pnl(existing.avg_entry_price, fill_price, quantity, fee)
        new_quantity = existing.quantity - quantity
        status: PositionStatus = "CLOSED" if new_quantity == 0 else "OPEN"
        return PositionUpdateResult(
            new_quantity=new_quantity,
            new_avg_entry_price=existing.avg_entry_price,
            realized_pnl_delta=realized,
            status=status,
        )
