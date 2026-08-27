"""Integration tests: PaperTradingService against a live Postgres.
Requires `docker compose up -d postgres redis` — auto-skipped otherwise
(see tests/conftest.py db_engine).

`paper_accounts` is a single, process-wide-shared row (like Phase 6's
active `RiskPolicy`) and `paper_positions` is at-most-one-open-row-per-
asset — both persist across every test in the whole suite. Tests here
follow the same discipline Phase 6 established:

- A `Signal` + `RiskEvaluation` pair is constructed directly (bypassing
  the full Signal Engine -> Risk Engine pipeline) so each test controls
  the exact approved quantity, keeping trades small and predictable
  regardless of what other tests have already done to the shared
  account/positions.
- Assertions compare *before/after deltas* or values *read back from the
  row the code under test just wrote* (e.g. the fill's own recorded
  price/fee), never a hardcoded absolute cash/equity figure — the
  account's exact balance depends on every test that ran before it.
- A position-does-not-exist scenario is constructed by closing a
  position this same test just opened, not by assuming a symbol was
  never touched by another test.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.asset import Asset
from app.models.paper_trading import PaperAccount, PaperFill, PaperOrder, PaperPosition
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.paper_trading import pricing
from app.services.paper_trading.execution import PaperExecutionAdapter
from app.services.paper_trading.service import PaperTradingService

FEE_RATE = Decimal("0.001")


def _service(db_session) -> PaperTradingService:
    market_data = MarketDataService(db_session)
    execution_adapter = PaperExecutionAdapter(market_data, FEE_RATE)
    return PaperTradingService(db_session, execution_adapter, market_data)


async def _make_risk_approved_signal(
    db_session, symbol: str, quantity: Decimal, *, signal_type: str = "BUY"
) -> Signal:
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one()
    policy_result = await db_session.execute(
        select(RiskPolicy).where(RiskPolicy.is_active.is_(True))
    )
    policy = policy_result.scalar_one()

    signal = Signal(
        asset_id=asset.id,
        interval="1d",
        signal=signal_type,
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG",
        market_regime="BULLISH",
        reasons=["test fixture signal"],
        supporting_features={"rsi14": 55.0},
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


async def _get_account(db_session) -> PaperAccount:
    result = await db_session.execute(select(PaperAccount).limit(1))
    return result.scalar_one()


async def _get_fill_for_order(db_session, order_id: uuid.UUID) -> PaperFill:
    result = await db_session.execute(select(PaperFill).where(PaperFill.order_id == order_id))
    return result.scalar_one()


# --- execute_signal: happy path (Step 29 "TEST ORDER FLOW") ---------------


@pytest.mark.asyncio
async def test_execute_signal_creates_order_fill_and_position(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    service = _service(db_session)
    account_before = await _get_account(db_session)
    cash_before = account_before.cash

    order = await service.execute_signal(signal.id)

    assert order.status == "FILLED"
    assert order.side == "BUY"
    assert order.signal_id == signal.id
    assert order.filled_quantity == Decimal("1")
    assert order.average_fill_price is not None
    assert order.filled_at is not None

    fill = await _get_fill_for_order(db_session, order.id)
    assert fill.quantity == Decimal("1")
    assert fill.fill_price == order.average_fill_price
    assert fill.realized_pnl is None  # opening fill never realizes P/L

    await db_session.refresh(account_before)
    expected_cash = cash_before - (fill.quantity * fill.fill_price + fill.fee)
    assert account_before.cash == expected_cash

    position_result = await db_session.execute(
        select(PaperPosition).where(
            PaperPosition.asset_id == signal.asset_id, PaperPosition.status == "OPEN"
        )
    )
    position = position_result.scalars().first()
    assert position is not None
    assert position.quantity >= Decimal("1")


@pytest.mark.asyncio
async def test_execute_signal_fee_matches_configured_rate(db_session) -> None:
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("1"))
    service = _service(db_session)

    order = await service.execute_signal(signal.id)
    fill = await _get_fill_for_order(db_session, order.id)

    expected_fee = pricing.compute_fee(fill.quantity * fill.fill_price, FEE_RATE)
    assert fill.fee == expected_fee


@pytest.mark.asyncio
async def test_execute_signal_increasing_an_existing_position_uses_weighted_average(
    db_session,
) -> None:
    first_signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("2"))
    service = _service(db_session)
    first_order = await service.execute_signal(first_signal.id)
    first_fill = await _get_fill_for_order(db_session, first_order.id)

    position_result = await db_session.execute(
        select(PaperPosition).where(
            PaperPosition.asset_id == first_signal.asset_id, PaperPosition.status == "OPEN"
        )
    )
    position_after_first = position_result.scalar_one()
    quantity_before = position_after_first.quantity
    avg_before = position_after_first.avg_entry_price

    second_signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("3"))
    second_order = await service.execute_signal(second_signal.id)
    second_fill = await _get_fill_for_order(db_session, second_order.id)

    await db_session.refresh(position_after_first)
    expected_avg = pricing.compute_weighted_average_entry(
        quantity_before, avg_before, second_fill.quantity, second_fill.fill_price
    )
    assert position_after_first.quantity == quantity_before + Decimal("3")
    assert position_after_first.avg_entry_price == expected_avg
    assert first_fill.fee >= 0 and second_fill.fee >= 0  # sanity: both fills recorded a fee


# --- idempotency (Step 19/30) ----------------------------------------------


@pytest.mark.asyncio
async def test_execute_signal_twice_raises_conflict_and_creates_only_one_order(
    db_session,
) -> None:
    signal = await _make_risk_approved_signal(db_session, "AMZN", Decimal("1"))
    service = _service(db_session)

    await service.execute_signal(signal.id)
    with pytest.raises(ConflictError):
        await service.execute_signal(signal.id)

    result = await db_session.execute(select(PaperOrder).where(PaperOrder.signal_id == signal.id))
    orders = result.scalars().all()
    assert len(orders) == 1

    fills_result = await db_session.execute(
        select(PaperFill).where(PaperFill.order_id == orders[0].id)
    )
    assert len(fills_result.scalars().all()) == 1


# --- rejection cases (Step 21/29) -------------------------------------------


@pytest.mark.asyncio
async def test_execute_candidate_signal_raises_conflict(db_session) -> None:
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == "TSLA"))
    asset = asset_result.scalar_one()
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
        status="CANDIDATE",
        generated_at=datetime.now(UTC),
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    service = _service(db_session)
    with pytest.raises(ConflictError):
        await service.execute_signal(signal.id)


@pytest.mark.asyncio
async def test_execute_risk_rejected_signal_raises_conflict(db_session) -> None:
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == "AAPL"))
    asset = asset_result.scalar_one()
    signal = Signal(
        asset_id=asset.id,
        interval="1h",
        signal="SELL",
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength=None,
        market_regime="BEARISH",
        reasons=["test fixture signal"],
        supporting_features={},
        invalidating_conditions=[],
        status="RISK_REJECTED",
        generated_at=datetime.now(UTC),
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)

    service = _service(db_session)
    with pytest.raises(ConflictError):
        await service.execute_signal(signal.id)


@pytest.mark.asyncio
async def test_execute_unknown_signal_raises_not_found(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.execute_signal(uuid.uuid4())


@pytest.mark.asyncio
async def test_execute_signal_with_no_risk_evaluation_raises_app_error(db_session) -> None:
    # A RISK_APPROVED status with no backing RiskEvaluation row is a data
    # integrity violation that should never happen through the real
    # pipeline (RiskService writes both in one transaction) — constructed
    # here deliberately to prove the defensive check fires.
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == "MSFT"))
    asset = asset_result.scalar_one()
    signal = Signal(
        asset_id=asset.id,
        interval="5m",
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
    await db_session.commit()
    await db_session.refresh(signal)

    service = _service(db_session)
    with pytest.raises(AppError):
        await service.execute_signal(signal.id)


@pytest.mark.asyncio
async def test_execute_signal_with_absurd_quantity_is_rejected_for_insufficient_cash(
    db_session,
) -> None:
    signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("100000000"))
    service = _service(db_session)

    order = await service.execute_signal(signal.id)

    assert order.status == "REJECTED"
    assert order.rejection_reason is not None
    assert "insufficient cash" in order.rejection_reason.lower()
    fills_result = await db_session.execute(select(PaperFill).where(PaperFill.order_id == order.id))
    assert fills_result.scalars().first() is None  # no fill for a rejected order


# --- close_position (Step 10/11/29) -----------------------------------------


@pytest.mark.asyncio
async def test_close_position_realizes_pnl_and_frees_up_the_symbol(db_session) -> None:
    # TSLA is also traded (opened, never closed) by other test files
    # (test_api_paper.py, test_paper_data_consistency.py) — this test's
    # own BUY may only be adding to an already-open position, so the
    # position's *actual* quantity/average-entry (captured right before
    # the close, reflecting every contributor) is what the close must be
    # measured against, not this test's own single fill in isolation.
    signal = await _make_risk_approved_signal(db_session, "TSLA", Decimal("2"))
    service = _service(db_session)
    await service.execute_signal(signal.id)

    position_before_close_result = await db_session.execute(
        select(PaperPosition).where(
            PaperPosition.asset_id == signal.asset_id, PaperPosition.status == "OPEN"
        )
    )
    position_before_close = position_before_close_result.scalar_one()
    quantity_before_close = position_before_close.quantity
    avg_entry_before_close = position_before_close.avg_entry_price

    account_before_close = await _get_account(db_session)
    cash_before_close = account_before_close.cash

    close_order = await service.close_position("TSLA")

    assert close_order.side == "SELL"
    assert close_order.signal_id is None
    assert close_order.status == "FILLED"
    assert close_order.filled_quantity == quantity_before_close

    close_fill = await _get_fill_for_order(db_session, close_order.id)
    assert close_fill.realized_pnl is not None
    expected_pnl = pricing.compute_realized_pnl(
        avg_entry_before_close, close_fill.fill_price, close_fill.quantity, close_fill.fee
    )
    assert close_fill.realized_pnl == expected_pnl

    await db_session.refresh(account_before_close)
    expected_cash = cash_before_close + (
        close_fill.quantity * close_fill.fill_price - close_fill.fee
    )
    assert account_before_close.cash == expected_cash

    position_result = await db_session.execute(
        select(PaperPosition)
        .where(PaperPosition.asset_id == signal.asset_id)
        .order_by(PaperPosition.opened_at.desc())
        .limit(1)
    )
    position = position_result.scalar_one()
    assert position.status == "CLOSED"
    assert position.quantity == Decimal("0")
    assert position.closed_at is not None

    # The symbol is now free — closing again finds nothing to close.
    with pytest.raises(NotFoundError):
        await service.close_position("TSLA")


@pytest.mark.asyncio
async def test_close_position_with_no_open_position_raises_not_found(db_session) -> None:
    # Open-then-close first so this assertion doesn't depend on whether
    # another test happened to touch this symbol already.
    signal = await _make_risk_approved_signal(db_session, "AMZN", Decimal("1"))
    service = _service(db_session)
    await service.execute_signal(signal.id)
    await service.close_position("AMZN")

    with pytest.raises(NotFoundError):
        await service.close_position("AMZN")


@pytest.mark.asyncio
async def test_close_position_unknown_symbol_raises_not_found(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.close_position("NOSUCHSYMBOL")
