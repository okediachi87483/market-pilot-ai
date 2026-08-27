"""Transaction-integrity tests (Step 20/31): a failure partway through
`execute_signal`/`close_position` must leave no partial financial state
— no order without its fill, no fill without a position/cash update.
Simulated by patching the engine to raise *after* the order has been
staged (`db.add` + `flush`) but *before* the final `commit()` — proving
the uncommitted work never became durable, not just that the exception
propagated."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.asset import Asset
from app.models.paper_trading import PaperAccount, PaperFill, PaperOrder
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.paper_trading.execution import PaperExecutionAdapter
from app.services.paper_trading.service import PaperTradingService

FEE_RATE = Decimal("0.001")


def _service(db_session) -> PaperTradingService:
    market_data = MarketDataService(db_session)
    execution_adapter = PaperExecutionAdapter(market_data, FEE_RATE)
    return PaperTradingService(db_session, execution_adapter, market_data)


async def _make_risk_approved_signal(db_session, symbol: str, quantity: Decimal) -> Signal:
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one()
    policy_result = await db_session.execute(
        select(RiskPolicy).where(RiskPolicy.is_active.is_(True))
    )
    policy = policy_result.scalar_one()

    signal = Signal(
        asset_id=asset.id,
        interval="1d",
        signal="BUY",
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG",
        market_regime="BULLISH",
        reasons=["test fixture signal"],
        supporting_features={},
        invalidating_conditions=[],
        status="RISK_APPROVED",
        generated_at=datetime.now(UTC),
    )
    db_session.add(signal)
    await db_session.flush()

    evaluation = RiskEvaluation(
        signal_id=signal.id,
        policy_id=policy.id,
        policy_version=policy.version,
        decision="APPROVED",
        reasons=[],
        checks=[],
        calculated_position_size=quantity,
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("98.00"),
        take_profit_price=Decimal("104.00"),
        position_value=quantity * Decimal("100.00"),
        portfolio_snapshot={},
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


@pytest.mark.asyncio
async def test_execute_signal_failure_during_position_update_rolls_back_everything(
    db_session,
) -> None:
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    service = _service(db_session)

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    cash_before = account_result.scalar_one().cash

    signal_id = signal.id

    with patch.object(
        service.engine, "apply_buy_fill", side_effect=RuntimeError("simulated failure")
    ):
        with pytest.raises(RuntimeError):
            await service.execute_signal(signal_id)

    await db_session.rollback()

    orders_result = await db_session.execute(
        select(PaperOrder).where(PaperOrder.signal_id == signal_id)
    )
    assert (
        orders_result.scalars().first() is None
    ), "no order should survive a rolled-back transaction"

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    assert account_result.scalar_one().cash == cash_before, "cash must be unchanged"


@pytest.mark.asyncio
async def test_close_position_failure_during_position_update_rolls_back_everything(
    db_session,
) -> None:
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("1"))
    service = _service(db_session)
    open_order = await service.execute_signal(signal.id)
    open_order_id = open_order.id
    open_order_asset_id = open_order.asset_id

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    cash_before_close_attempt = account_result.scalar_one().cash

    # MSFT's asset_id is shared with any other test that also happens to
    # trade MSFT, so "only one order for this asset" isn't a safe
    # assertion — capture the exact set of order ids that exist for this
    # asset right before the failed close, and confirm that exact set is
    # unchanged afterward (no new order id appeared).
    before_result = await db_session.execute(
        select(PaperOrder.id).where(PaperOrder.asset_id == open_order_asset_id)
    )
    order_ids_before = set(before_result.scalars().all())

    with patch.object(
        service.engine, "apply_sell_fill", side_effect=RuntimeError("simulated failure")
    ):
        with pytest.raises(RuntimeError):
            await service.close_position("MSFT")

    await db_session.rollback()

    after_result = await db_session.execute(
        select(PaperOrder.id).where(PaperOrder.asset_id == open_order_asset_id)
    )
    order_ids_after = set(after_result.scalars().all())
    assert order_ids_after == order_ids_before, "no new order should survive a rolled-back close"

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    assert account_result.scalar_one().cash == cash_before_close_attempt

    fills_result = await db_session.execute(
        select(PaperFill).where(PaperFill.order_id == open_order_id)
    )
    assert len(fills_result.scalars().all()) == 1  # only the original opening fill
