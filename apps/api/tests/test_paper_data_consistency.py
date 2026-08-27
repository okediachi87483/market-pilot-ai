"""Data-consistency tests (Step 28) — proving the database CHECK
constraints and partial-unique indexes in app/models/paper_trading.py
actually reject the states they're meant to reject, not just document
an intention. Requires a live Postgres."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.asset import Asset
from app.models.paper_trading import PaperAccount, PaperFill, PaperOrder, PaperPosition
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
async def test_account_cash_cannot_go_negative(db_session) -> None:
    result = await db_session.execute(select(PaperAccount).limit(1))
    account = result.scalar_one()
    account.cash = Decimal("-1")
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_position_quantity_cannot_go_negative(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    service = _service(db_session)
    await service.execute_signal(signal.id)

    result = await db_session.execute(
        select(PaperPosition).where(
            PaperPosition.asset_id == signal.asset_id, PaperPosition.status == "OPEN"
        )
    )
    position = result.scalar_one()
    position.quantity = Decimal("-1")
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_order_filled_quantity_cannot_exceed_ordered_quantity(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("1"))
    service = _service(db_session)
    order = await service.execute_signal(signal.id)

    order.filled_quantity = order.quantity + Decimal("1")
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_at_most_one_open_position_per_asset(db_session) -> None:
    # Directly attempting to insert a second OPEN row for an asset that
    # already has one must violate the partial unique index — proves the
    # constraint is real, independent of whether application code would
    # ever try this (it doesn't: PaperTradingService always looks up the
    # existing OPEN row and updates it in place).
    signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("1"))
    service = _service(db_session)
    await service.execute_signal(signal.id)

    duplicate = PaperPosition(
        asset_id=signal.asset_id,
        quantity=Decimal("1"),
        avg_entry_price=Decimal("100.00"),
        realized_pnl=Decimal("0"),
        status="OPEN",
        opened_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_closed_position_has_zero_quantity_after_a_full_close(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "AMZN", Decimal("1"))
    service = _service(db_session)
    await service.execute_signal(signal.id)
    await service.close_position("AMZN")

    result = await db_session.execute(
        select(PaperPosition)
        .where(PaperPosition.asset_id == signal.asset_id)
        .order_by(PaperPosition.opened_at.desc())
        .limit(1)
    )
    position = result.scalar_one()
    assert position.status == "CLOSED"
    assert position.quantity == Decimal("0")


@pytest.mark.asyncio
async def test_a_filled_order_always_has_at_least_one_fill(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "TSLA", Decimal("1"))
    service = _service(db_session)
    order = await service.execute_signal(signal.id)

    assert order.status == "FILLED"
    result = await db_session.execute(select(PaperFill).where(PaperFill.order_id == order.id))
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_portfolio_equity_reconciles_with_cash_plus_market_value(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    service = _service(db_session)
    await service.execute_signal(signal.id)

    state = await service.get_portfolio_state()
    assert state.equity == state.cash + state.market_value


@pytest.mark.asyncio
async def test_signal_id_uniqueness_is_enforced_at_the_database_level(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("1"))
    service = _service(db_session)
    order = await service.execute_signal(signal.id)

    asset_result = await db_session.execute(select(Asset).where(Asset.id == order.asset_id))
    asset = asset_result.scalar_one()
    duplicate_order = PaperOrder(
        id=uuid.uuid4(),
        signal_id=signal.id,
        asset_id=asset.id,
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1"),
        requested_price=Decimal("100.00"),
        status="PENDING",
    )
    db_session.add(duplicate_order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
