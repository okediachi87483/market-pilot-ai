"""The one authoritative portfolio-state computation (Step 13/14/17) —
called by both the paper-trading API (the full picture) and
`risk_engine.portfolio_state.PortfolioStateProvider` (which maps the
relevant subset into its own narrower `PortfolioSnapshot` shape). A
single computation avoids two independent implementations of "walk open
positions, sum market value, sum today's realized P/L" ever drifting
apart.

Not a pure function — it reads the database and current market prices —
but it takes no signal/order-specific state, only `db` and
`market_data_service`, mirroring the "impure edge, pure core" split the
rest of this codebase uses (`SignalService`, `RiskService`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.paper_trading import PaperAccount, PaperFill, PaperPosition
from app.services.market_data.service import MarketDataService
from app.services.paper_trading import pricing

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PositionMarketData:
    position: PaperPosition
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class PortfolioState:
    starting_equity: Decimal
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl_total: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    daily_pnl: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    open_position_count: int
    last_losing_trade_at: datetime | None
    as_of: datetime
    positions: list[PositionMarketData]


async def get_account(db: AsyncSession) -> PaperAccount:
    result = await db.execute(select(PaperAccount).limit(1))
    account = result.scalar_one_or_none()
    if account is None:
        # Should never happen — the initial migration seeds exactly one
        # account row, and nothing ever deletes it. Surfacing this as a
        # clear 500 rather than fabricating a portfolio out of nothing
        # (Step 8: "do not create money out of thin air").
        raise AppError("no paper trading account is configured")
    return account


async def compute_portfolio_state(
    db: AsyncSession, market_data_service: MarketDataService
) -> PortfolioState:
    account = await get_account(db)

    result = await db.execute(select(PaperPosition).where(PaperPosition.status == "OPEN"))
    open_positions = list(result.scalars().all())

    positions_with_market_data: list[PositionMarketData] = []
    market_value_total = Decimal("0")
    unrealized_total = Decimal("0")
    for position in open_positions:
        _asset, market_data_row = await market_data_service.get_quote(position.asset.symbol)
        current_price = market_data_row.close
        market_value = position.quantity * current_price
        unrealized = pricing.compute_unrealized_pnl(
            position.avg_entry_price, current_price, position.quantity
        )
        positions_with_market_data.append(
            PositionMarketData(position, current_price, market_value, unrealized)
        )
        market_value_total += market_value
        unrealized_total += unrealized

    equity = account.cash + market_value_total

    # Peak-equity ratchet (Step 15): every computation of current equity
    # is an opportunity to observe a new high, not only a trade — price
    # movement on an open position can set one too. A narrow, isolated
    # commit: nothing else is ever staged on `db` before this point in
    # either caller (RiskService.evaluate_signal, GET /paper/portfolio).
    if equity > account.peak_equity:
        account.peak_equity = equity
        await db.commit()
    peak_equity = account.peak_equity

    drawdown_pct = (
        ((peak_equity - equity) / peak_equity * HUNDRED) if peak_equity > 0 else Decimal("0")
    )

    realized_total_row = await db.execute(
        select(func.coalesce(func.sum(PaperFill.realized_pnl), 0)).where(
            PaperFill.realized_pnl.isnot(None)
        )
    )
    realized_pnl_total = realized_total_row.scalar_one() or Decimal("0")

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_row = await db.execute(
        select(func.coalesce(func.sum(PaperFill.realized_pnl), 0)).where(
            PaperFill.realized_pnl.isnot(None), PaperFill.timestamp >= today_start
        )
    )
    daily_pnl = daily_row.scalar_one() or Decimal("0")

    last_loss_row = await db.execute(
        select(PaperFill.timestamp)
        .where(PaperFill.realized_pnl.isnot(None), PaperFill.realized_pnl < 0)
        .order_by(PaperFill.timestamp.desc())
        .limit(1)
    )
    last_losing_trade_at = last_loss_row.scalar_one_or_none()

    return PortfolioState(
        starting_equity=account.starting_equity,
        cash=account.cash,
        market_value=market_value_total,
        equity=equity,
        realized_pnl_total=realized_pnl_total,
        unrealized_pnl=unrealized_total,
        total_pnl=realized_pnl_total + unrealized_total,
        daily_pnl=daily_pnl,
        peak_equity=peak_equity,
        drawdown_pct=drawdown_pct,
        open_position_count=len(open_positions),
        last_losing_trade_at=last_losing_trade_at,
        as_of=datetime.now(UTC),
        positions=positions_with_market_data,
    )


async def get_position_market_data(
    db: AsyncSession, market_data_service: MarketDataService, position: PaperPosition
) -> PositionMarketData:
    """Single-position variant of the same computation, for a closed
    position (excluded from `compute_portfolio_state`'s open-only walk)
    or when only one position's detail is needed."""
    _asset, market_data_row = await market_data_service.get_quote(position.asset.symbol)
    current_price = market_data_row.close
    market_value = position.quantity * current_price
    unrealized = pricing.compute_unrealized_pnl(
        position.avg_entry_price, current_price, position.quantity
    )
    return PositionMarketData(position, current_price, market_value, unrealized)
