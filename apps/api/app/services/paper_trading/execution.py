"""The execution boundary (Step 18):

    ExecutionEngine (this module's Protocol)
            |
            v
    PaperExecutionAdapter (the only implementation)

Conceptually the same shape a future `RealBrokerAdapter` would occupy —
`PaperTradingService` depends only on the `ExecutionAdapter` protocol,
never on `PaperExecutionAdapter` directly, so a real broker integration
later is a second implementation of this interface, not a rewrite of the
service (mirrors `docs/architecture.md`'s `BrokerAdapter` principle from
[ADR-007](../../../../docs/decisions/ADR-007-paper-trading-first.md)).
**No real broker adapter is implemented in this phase** — this is the
one and only concrete class.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from app.services.market_data.service import MarketDataService
from app.services.paper_trading import pricing
from app.services.paper_trading.types import FillCalculation, OrderSide


class ExecutionAdapter(Protocol):
    async def fill(self, symbol: str, side: OrderSide, quantity: Decimal) -> FillCalculation: ...


class PaperExecutionAdapter:
    """Simulates a MARKET order fill (Step 6): the fill price is always
    the current market price, for both BUY and SELL — no slippage model
    is implemented (the architecture allows one, deterministic-only, but
    none is required, and adding one now would be unrequested complexity
    — documented as a limitation in docs/paper-trading.md). Fees are
    computed from the configured, deterministic `paper_trading_fee_rate`
    (Step 7) — never a hard-coded rate."""

    def __init__(self, market_data_service: MarketDataService, fee_rate: Decimal) -> None:
        self.market_data_service = market_data_service
        self.fee_rate = fee_rate

    async def fill(self, symbol: str, side: OrderSide, quantity: Decimal) -> FillCalculation:
        _asset, market_data_row = await self.market_data_service.get_quote(symbol)
        price = market_data_row.close
        notional = pricing.compute_notional(quantity, price)
        fee = pricing.compute_fee(notional, self.fee_rate)
        return FillCalculation(price=price, fee=fee, notional=notional)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)
