"""Where `PortfolioSnapshot` comes from — the Risk Engine's read-only
view onto the real paper-trading account.

**Phase 7 update**: this used to return a clean, position-free default
(Phase 6, before paper trading existed) — see git history / the Phase 6
completion report for that version. It now delegates to
`app.services.paper_trading.portfolio.compute_portfolio_state`, the one
authoritative computation over `paper_accounts`/`paper_positions`/
`paper_fills`, and maps the fields the Risk Engine's check pipeline
actually needs into `risk_engine.types.PortfolioSnapshot`. No caller of
`get_snapshot()` (`RiskService`) needed to change — this is exactly the
seam Phase 6 documented in advance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.service import MarketDataService
from app.services.paper_trading.portfolio import compute_portfolio_state
from app.services.risk_engine.types import PortfolioSnapshot


class PortfolioStateProvider:
    def __init__(self, db: AsyncSession, market_data_service: MarketDataService) -> None:
        self.db = db
        self.market_data_service = market_data_service

    async def get_snapshot(self, *, as_of: datetime | None = None) -> PortfolioSnapshot:
        state = await compute_portfolio_state(self.db, self.market_data_service)
        return PortfolioSnapshot(
            equity=state.equity,
            cash=state.cash,
            high_water_mark=state.peak_equity,
            open_position_count=state.open_position_count,
            open_position_value=state.market_value,
            realized_pl_today=state.daily_pnl,
            last_losing_trade_at=state.last_losing_trade_at,
            as_of=as_of or datetime.now(UTC),
        )
