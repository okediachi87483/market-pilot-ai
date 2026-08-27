"""Where `PortfolioSnapshot` comes from today — and the seam Phase 7
(paper trading) will replace.

There is no `positions`/`trades`/`orders` table yet (Phase 7 builds
them). Steps 12/13/14/15/16 all describe checks against "authoritative
backend state" — exposure, concurrent positions, daily realized P/L,
drawdown, and the last losing trade's timestamp. Until real trading
activity exists, the only honest authoritative answer for all of those
is: a clean, fully-funded, position-free portfolio. This is not a
placeholder computation faked to look real — it *is* the real state of
an account that has never traded, computed the same way it always will
be once Phase 7 exists: equity/cash start from the account's starting
balance, and every other field derives from position/trade history that
is, today, genuinely empty.

`PortfolioStateProvider` is the seam: `RiskService` depends on this
class's `get_snapshot()` method, not on how it's computed. Phase 7 swaps
this implementation for one that aggregates real `positions`/`trades`
rows — no caller of `get_snapshot()` needs to change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import Settings
from app.services.risk_engine.types import PortfolioSnapshot


class PortfolioStateProvider:
    def __init__(self, settings: Settings) -> None:
        self._starting_equity = settings.risk_starting_equity

    async def get_snapshot(self, *, as_of: datetime | None = None) -> PortfolioSnapshot:
        as_of = as_of or datetime.now(UTC)
        equity = self._starting_equity
        return PortfolioSnapshot(
            equity=equity,
            cash=equity,
            high_water_mark=equity,
            open_position_count=0,
            open_position_value=Decimal("0"),
            realized_pl_today=Decimal("0"),
            last_losing_trade_at=None,
            as_of=as_of,
        )
