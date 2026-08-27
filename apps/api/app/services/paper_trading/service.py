"""PaperTradingService — ties `PaperTradingEngine` to the database: the
only piece in this package that knows about SQLAlchemy, `Signal`, or
`RiskEvaluation`. Two entry points create financial state,
`execute_signal` (Step 19: idempotent on `signal_id`) and
`close_position` (a direct, non-signal-driven action) — both follow the
same shape: compute everything first, then stage every write (order,
fill, position, account) on the session and commit exactly once (Step
20), so a `FILLED` order can never exist without its fill, position
update, and cash update also having landed in the same transaction.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.paper_trading import PaperFill, PaperOrder, PaperPosition
from app.models.risk import RiskEvaluation
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.paper_trading import portfolio as portfolio_module
from app.services.paper_trading.engine import PaperTradingEngine
from app.services.paper_trading.execution import ExecutionAdapter
from app.services.paper_trading.portfolio import PortfolioState, PositionMarketData
from app.services.paper_trading.types import InsufficientPositionError, PositionSnapshot

logger = get_logger(__name__)


class PaperTradingService:
    def __init__(
        self,
        db: AsyncSession,
        execution_adapter: ExecutionAdapter,
        market_data_service: MarketDataService,
    ) -> None:
        self.db = db
        self.execution_adapter = execution_adapter
        self.market_data_service = market_data_service
        self.engine = PaperTradingEngine()

    # --- execution ---------------------------------------------------

    async def execute_signal(self, signal_id: uuid.UUID) -> PaperOrder:
        """Only a `RISK_APPROVED` signal may become a paper order (the
        architecture's own hard rule — a `CANDIDATE` or `RISK_REJECTED`
        signal is refused with `409`, never silently accepted). At most
        one order per signal, ever (Step 19) — a second call for the
        same `signal_id` is also a `409`, not a silent no-op, matching
        the same re-evaluation-refusal precedent `RiskService` already
        set in Phase 6."""
        started = time.monotonic()

        signal = await self._get_signal(signal_id)

        existing_order = await self._get_order_by_signal_id(signal_id)
        if existing_order is not None:
            raise ConflictError(
                f"signal {signal_id} already has a paper order",
                details={"signal_id": str(signal_id), "order_id": str(existing_order.id)},
            )
        if signal.status != "RISK_APPROVED":
            raise ConflictError(
                f"signal {signal_id} is {signal.status!r}, not RISK_APPROVED — only a "
                "risk-approved signal may become a paper order",
                details={"signal_id": str(signal_id), "status": signal.status},
            )

        risk_evaluation = await self._get_latest_approval(signal_id)
        if risk_evaluation is None or risk_evaluation.calculated_position_size is None:
            raise AppError(
                "signal is RISK_APPROVED but has no usable risk evaluation",
                details={"signal_id": str(signal_id)},
            )
        quantity = risk_evaluation.calculated_position_size
        if quantity <= 0:
            raise ValidationAppError(
                "approved position size must be positive",
                details={"signal_id": str(signal_id), "quantity": str(quantity)},
            )

        # `fill()` must run BEFORE any lock is acquired: it goes through
        # MarketDataService.get_quote(), which eagerly persists (and
        # *commits*) any freshly-ingested market data. A commit ends the
        # current transaction and releases every row lock held so far —
        # so if a lock were taken first, this call would silently drop it
        # before the read-modify-write below ever runs, reopening the
        # exact race the locks exist to close (caught directly by
        # tests/test_paper_concurrency.py). `quantity` here comes only
        # from the risk evaluation, not from any locked row, so calling
        # this first is safe — nothing below depends on it having
        # happened after the locks.
        fill = await self.execution_adapter.fill(signal.asset.symbol, "BUY", quantity)

        # Lock ordering matters: close_position locks position-then-account
        # (it needs to know if there's anything to close before bothering
        # to lock the shared cash row), so this method acquires the same
        # two locks in the same order — position, then account — to avoid
        # a lock-ordering deadlock between the two write paths under real
        # concurrency (Postgres would otherwise be free to grant execute_signal
        # the account lock while close_position holds the position lock, and
        # vice versa, each waiting on the other). Nothing between here and
        # the final commit() below calls fill()/get_quote() again, so these
        # locks are held continuously through to the commit.
        existing_position = await self._get_open_position(signal.asset_id)
        account = await portfolio_module.get_account_for_update(self.db)

        now = datetime.now(UTC)
        order = PaperOrder(
            signal_id=signal.id,
            asset_id=signal.asset_id,
            side="BUY",
            order_type="MARKET",
            quantity=quantity,
            requested_price=fill.price,
            status="PENDING",
            submitted_at=now,
        )
        self.db.add(order)
        try:
            await self.db.flush()  # order.id needed for the fill's FK
        except IntegrityError as exc:
            # A genuine race: two concurrent calls both passed the
            # `_get_order_by_signal_id` check above before either
            # committed. `paper_orders.signal_id` is UNIQUE at the
            # database level (docs/paper-trading.md §15) — that
            # constraint is what actually prevents the duplicate order,
            # this except only translates the resulting IntegrityError
            # into the same clean 409 a sequential second call already
            # gets, instead of leaking a raw database error as a 500.
            await self.db.rollback()
            raise ConflictError(
                f"signal {signal_id} already has a paper order",
                details={"signal_id": str(signal_id)},
            ) from exc

        required_cash = fill.notional + fill.fee
        if required_cash > account.cash:
            order.status = "REJECTED"
            order.rejection_reason = (
                f"insufficient cash: required {required_cash}, available {account.cash}"
            )
            await self.db.commit()
            await self.db.refresh(order)
            logger.info(
                "paper order rejected signal_id=%s symbol=%s reason=insufficient_cash "
                "required=%s available=%s",
                signal_id,
                signal.asset.symbol,
                required_cash,
                account.cash,
            )
            return order

        existing_snapshot = (
            PositionSnapshot(existing_position.quantity, existing_position.avg_entry_price)
            if existing_position
            else None
        )
        update = self.engine.apply_buy_fill(existing_snapshot, quantity, fill.price)

        fill_row = PaperFill(
            order_id=order.id,
            asset_id=signal.asset_id,
            side="BUY",
            quantity=quantity,
            fill_price=fill.price,
            fee=fill.fee,
            realized_pnl=None,
            timestamp=now,
        )
        self.db.add(fill_row)

        if existing_position is None:
            self.db.add(
                PaperPosition(
                    asset_id=signal.asset_id,
                    quantity=update.new_quantity,
                    avg_entry_price=update.new_avg_entry_price,
                    realized_pnl=Decimal("0"),
                    status="OPEN",
                    opened_at=now,
                    updated_at=now,
                )
            )
        else:
            existing_position.quantity = update.new_quantity
            existing_position.avg_entry_price = update.new_avg_entry_price
            existing_position.updated_at = now

        account.cash -= required_cash
        account.updated_at = now

        order.status = "FILLED"
        order.filled_quantity = quantity
        order.average_fill_price = fill.price
        order.filled_at = now

        await self.db.commit()
        await self.db.refresh(order)
        await self.db.refresh(fill_row)

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "paper order filled signal_id=%s order_id=%s fill_id=%s symbol=%s side=BUY "
            "quantity=%s fill_price=%s fee=%s duration_ms=%.1f",
            signal_id,
            order.id,
            fill_row.id,
            signal.asset.symbol,
            quantity,
            fill.price,
            fill.fee,
            duration_ms,
        )
        return order

    async def close_position(self, symbol: str) -> PaperOrder:
        """A direct, user-initiated action — not signal-driven
        (`order.signal_id` is `null`). Always closes the *entire*
        position (Step 22's suggested endpoint is a "close," not a
        partial reduce); the underlying engine supports a partial
        quantity too (exercised directly in unit tests, Step 10)."""
        started = time.monotonic()

        asset = await self._get_asset_by_symbol(symbol)

        # Provisional, *unlocked* read: only to learn a quantity to pass
        # into fill() below. execution_adapter.fill() goes through
        # MarketDataService.get_quote(), which eagerly commits — a lock
        # taken here would be silently released by that commit before
        # the real read-modify-write ever happens, exactly the race
        # tests/test_paper_concurrency.py exists to catch. The
        # authoritative, locked read happens after fill() returns.
        provisional_position = await self._get_open_position(asset.id, for_update=False)
        if provisional_position is None:
            raise NotFoundError(f"no open position for {symbol!r}", details={"symbol": symbol})
        provisional_quantity = provisional_position.quantity

        fill = await self.execution_adapter.fill(symbol, "SELL", provisional_quantity)

        # Lock ordering: position, then account — see execute_signal's
        # matching comment on why the order must agree across both
        # methods. Nothing after this point calls fill()/get_quote()
        # again, so both locks are held continuously through to commit().
        position = await self._get_open_position(asset.id)
        if position is None:
            raise NotFoundError(f"no open position for {symbol!r}", details={"symbol": symbol})
        if position.quantity != provisional_quantity:
            # A genuine race: something else (a concurrent BUY adding to
            # this position, most plausibly) changed the quantity between
            # the provisional read and this lock. The already-computed
            # `fill.fee`/`fill.notional` were sized for the stale
            # quantity and are not safe to reuse — rather than silently
            # mis-charge a fee, fail cleanly and ask the caller to retry
            # against the now-current state.
            raise ConflictError(
                f"position for {symbol!r} changed while closing it — retry",
                details={"symbol": symbol},
            )
        quantity_to_close = position.quantity
        account = await portfolio_module.get_account_for_update(self.db)

        existing_snapshot = PositionSnapshot(position.quantity, position.avg_entry_price)
        try:
            update = self.engine.apply_sell_fill(
                existing_snapshot, quantity_to_close, fill.price, fill.fee
            )
        except InsufficientPositionError as exc:
            raise ConflictError(str(exc), details={"symbol": symbol}) from exc

        now = datetime.now(UTC)
        order = PaperOrder(
            signal_id=None,
            asset_id=asset.id,
            side="SELL",
            order_type="MARKET",
            quantity=quantity_to_close,
            requested_price=fill.price,
            status="PENDING",
            submitted_at=now,
        )
        self.db.add(order)
        await self.db.flush()

        fill_row = PaperFill(
            order_id=order.id,
            asset_id=asset.id,
            side="SELL",
            quantity=quantity_to_close,
            fill_price=fill.price,
            fee=fill.fee,
            realized_pnl=update.realized_pnl_delta,
            timestamp=now,
        )
        self.db.add(fill_row)

        position.quantity = update.new_quantity
        position.avg_entry_price = update.new_avg_entry_price
        position.realized_pnl += update.realized_pnl_delta
        position.status = update.status
        position.updated_at = now
        if update.status == "CLOSED":
            position.closed_at = now

        account.cash += fill.notional - fill.fee
        account.updated_at = now

        order.status = "FILLED"
        order.filled_quantity = quantity_to_close
        order.average_fill_price = fill.price
        order.filled_at = now

        await self.db.commit()
        await self.db.refresh(order)
        await self.db.refresh(fill_row)

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "paper position closed symbol=%s order_id=%s fill_id=%s quantity=%s fill_price=%s "
            "fee=%s realized_pnl=%s duration_ms=%.1f",
            symbol,
            order.id,
            fill_row.id,
            quantity_to_close,
            fill.price,
            fill.fee,
            update.realized_pnl_delta,
            duration_ms,
        )
        return order

    # --- reads ---------------------------------------------------------

    async def get_portfolio_state(self) -> PortfolioState:
        return await portfolio_module.compute_portfolio_state(self.db, self.market_data_service)

    async def list_positions(self, *, status: str | None = None) -> list[PaperPosition]:
        stmt = select(PaperPosition)
        if status:
            stmt = stmt.where(PaperPosition.status == status)
        stmt = stmt.order_by(PaperPosition.opened_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_position_market_data(self, position: PaperPosition) -> PositionMarketData:
        return await portfolio_module.get_position_market_data(
            self.db, self.market_data_service, position
        )

    async def list_orders(
        self, *, symbol: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[PaperOrder]:
        stmt = select(PaperOrder)
        if symbol:
            stmt = stmt.join(PaperOrder.asset).where(Asset.symbol == symbol.strip().upper())
        if status:
            stmt = stmt.where(PaperOrder.status == status)
        stmt = stmt.order_by(PaperOrder.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_order(self, order_id: uuid.UUID) -> PaperOrder:
        result = await self.db.execute(select(PaperOrder).where(PaperOrder.id == order_id))
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError(
                f"unknown paper order id: {order_id}", details={"id": str(order_id)}
            )
        return order

    async def list_fills(
        self, *, symbol: str | None = None, order_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[PaperFill]:
        stmt = select(PaperFill)
        if symbol:
            stmt = stmt.join(PaperFill.asset).where(Asset.symbol == symbol.strip().upper())
        if order_id:
            stmt = stmt.where(PaperFill.order_id == order_id)
        stmt = stmt.order_by(PaperFill.timestamp.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # --- helpers ---------------------------------------------------------

    async def _get_signal(self, signal_id: uuid.UUID) -> Signal:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()
        if signal is None:
            raise NotFoundError(f"unknown signal id: {signal_id}", details={"id": str(signal_id)})
        return signal

    async def _get_order_by_signal_id(self, signal_id: uuid.UUID) -> PaperOrder | None:
        result = await self.db.execute(select(PaperOrder).where(PaperOrder.signal_id == signal_id))
        return result.scalar_one_or_none()

    async def _get_latest_approval(self, signal_id: uuid.UUID) -> RiskEvaluation | None:
        result = await self.db.execute(
            select(RiskEvaluation)
            .where(RiskEvaluation.signal_id == signal_id, RiskEvaluation.decision == "APPROVED")
            .order_by(RiskEvaluation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_open_position(
        self, asset_id: uuid.UUID, *, for_update: bool = True
    ) -> PaperPosition | None:
        # FOR UPDATE: only ever called from execute_signal/close_position
        # (both mutating paths). Without a row lock, two concurrent
        # requests against the same asset (two BUYs, two closes, or a
        # BUY racing a close) each read the same pre-mutation position,
        # both compute their own update against that stale snapshot, and
        # the second commit silently clobbers the first's — a lost
        # update, not just a duplicate row (caught by
        # tests/test_paper_concurrency.py). The lock makes the second
        # request block until the first's transaction ends, then see the
        # real current state (e.g. status already CLOSED) instead of a
        # stale copy. `for_update=False` exists only for a provisional,
        # pre-fill() read (close_position) that must not hold a lock
        # across the market-data commit inside execution_adapter.fill().
        stmt = select(PaperPosition).where(
            PaperPosition.asset_id == asset_id, PaperPosition.status == "OPEN"
        )
        if for_update:
            # `of=PaperPosition`: PaperPosition.asset is `lazy="joined"`
            # (a LEFT OUTER JOIN); plain `FOR UPDATE` can't lock across
            # the nullable side of an outer join (Postgres rejects it
            # outright), so the lock is scoped to just this table.
            #
            # `populate_existing()` is not optional: close_position's
            # provisional (unlocked) read a few lines earlier already put
            # this exact row into this session's identity map. Without
            # this, SQLAlchemy silently returns that *same stale Python
            # object* here instead of applying the freshly-locked row's
            # values — the quantity-mismatch race check right after this
            # call would then always compare a value against itself and
            # never detect a real race (proven via the identical failure
            # mode in RiskService._get_signal_for_update, fixed the same
            # way — see that comment for the full mechanism).
            stmt = stmt.with_for_update(of=PaperPosition).execution_options(populate_existing=True)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_asset_by_symbol(self, symbol: str) -> Asset:
        normalized = symbol.strip().upper()
        result = await self.db.execute(select(Asset).where(Asset.symbol == normalized))
        asset = result.scalar_one_or_none()
        if asset is None:
            raise NotFoundError(f"unknown asset symbol: {symbol!r}", details={"symbol": symbol})
        return asset
