"""Step 32 — proving the Phase 6 risk checks now react to real
paper-trading state instead of the Phase 6 clean-slate placeholder.

Both the active `RiskPolicy` (Phase 6) and the single `PaperAccount` row
(Phase 7) are process-wide singletons shared by the whole test suite.
Every test here that mutates either one captures the original values
first and restores them in a `finally` block, extending the exact
discipline `test_risk_service.py`'s `test_update_policy_...` already
established for the policy alone — see that file's module docstring.
Thresholds are deliberately set to an extreme (not just "lower") value
so the assertion holds regardless of what other tests already did to
the shared account (e.g. "reject if drawdown >= 0.01%" is true no
matter how many fee-paying trades already nudged equity below its
peak). Only the "rejects" direction of the cooldown check is exercised
here, not "passes once enough time elapses" — `close_position` tests
elsewhere in the suite can realize small real losses (fees exceeding a
tiny real price gain), so "the most recent loss is old enough" isn't a
safe assumption at the integration level; that direction is already
covered by pure tests in test_risk_checks.py
(test_loss_well_past_cooldown_passes,
test_loss_exactly_at_cooldown_boundary_passes).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.asset import Asset
from app.models.paper_trading import PaperAccount, PaperFill, PaperOrder, PaperPosition
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.paper_trading.execution import PaperExecutionAdapter
from app.services.paper_trading.service import PaperTradingService
from app.services.risk_engine.portfolio_state import PortfolioStateProvider
from app.services.risk_engine.service import RiskService

FEE_RATE = Decimal("0.001")


def _paper_service(db_session) -> PaperTradingService:
    market_data = MarketDataService(db_session)
    execution_adapter = PaperExecutionAdapter(market_data, FEE_RATE)
    return PaperTradingService(db_session, execution_adapter, market_data)


def _risk_service(db_session) -> RiskService:
    market_data = MarketDataService(db_session)
    portfolio_state_provider = PortfolioStateProvider(db_session, market_data)
    return RiskService(db_session, market_data, portfolio_state_provider)


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


async def _make_candidate_signal(db_session, symbol: str) -> Signal:
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
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
    return signal


async def _capture_policy_values(db_session) -> dict:
    result = await db_session.execute(select(RiskPolicy).where(RiskPolicy.is_active.is_(True)))
    policy = result.scalar_one()
    return {
        "enabled": policy.enabled,
        "max_position_size_pct": policy.max_position_size_pct,
        "max_portfolio_exposure_pct": policy.max_portfolio_exposure_pct,
        "max_daily_loss_pct": policy.max_daily_loss_pct,
        "max_drawdown_pct": policy.max_drawdown_pct,
        "stop_loss_pct": policy.stop_loss_pct,
        "take_profit_pct": policy.take_profit_pct,
        "risk_per_trade_pct": policy.risk_per_trade_pct,
        "max_concurrent_positions": policy.max_concurrent_positions,
        "cooldown_after_loss_minutes": policy.cooldown_after_loss_minutes,
    }


async def _ensure_at_least_one_open_position(db_session, symbol: str) -> None:
    result = await db_session.execute(select(PaperPosition).where(PaperPosition.status == "OPEN"))
    if result.scalars().first() is not None:
        return
    signal = await _make_risk_approved_signal(db_session, symbol, Decimal("1"))
    await _paper_service(db_session).execute_signal(signal.id)


async def _apply_synthetic_loss(
    db_session, amount: Decimal, when: datetime
) -> tuple[uuid.UUID, Decimal]:
    """Inserts a synthetic closing SELL fill (tied to a real order, so
    the FK is valid) recording a realized loss of `amount` at `when`,
    and moves that same amount out of the account's cash so equity
    genuinely reflects it (a bare `PaperFill` row alone wouldn't move
    `cash`). Returns `(fill_id, cash_before)` — the caller must remove
    the fill *and* restore cash in a `finally` block (`_undo_synthetic_
    loss`): `last_losing_trade_at` (docs/risk-engine.md's cooldown
    check) is a MAX over every `paper_fills` row ever written, so an
    orphaned synthetic loss would otherwise permanently poison the
    cooldown check for every later test (and every later run against
    the same persistent database)."""
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    order = await _paper_service(db_session).execute_signal(signal.id)

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    account = account_result.scalar_one()
    original_cash = account.cash

    order_result = await db_session.execute(select(PaperOrder).where(PaperOrder.id == order.id))
    persisted_order = order_result.scalar_one()
    synthetic_fill = PaperFill(
        order_id=persisted_order.id,
        asset_id=persisted_order.asset_id,
        side="SELL",
        quantity=Decimal("1"),
        fill_price=Decimal("1.00"),
        fee=Decimal("0"),
        realized_pnl=-amount,
        timestamp=when,
    )
    db_session.add(synthetic_fill)
    account.cash = account.cash - amount
    await db_session.commit()
    await db_session.refresh(synthetic_fill)
    return synthetic_fill.id, original_cash


async def _undo_synthetic_loss(db_session, fill_id: uuid.UUID, original_cash: Decimal) -> None:
    fill_result = await db_session.execute(select(PaperFill).where(PaperFill.id == fill_id))
    fill = fill_result.scalar_one()
    await db_session.delete(fill)

    account_result = await db_session.execute(select(PaperAccount).limit(1))
    account = account_result.scalar_one()
    account.cash = original_cash
    await db_session.commit()


@pytest.mark.asyncio
async def test_max_concurrent_positions_rejects_when_at_the_limit(db_session) -> None:
    await _ensure_at_least_one_open_position(db_session, "AAPL")
    risk_service = _risk_service(db_session)
    original = await _capture_policy_values(db_session)
    updated = dict(original)
    updated["max_concurrent_positions"] = 1

    try:
        await risk_service.update_policy(updated)
        candidate = await _make_candidate_signal(db_session, "MSFT")
        evaluation = await risk_service.evaluate_signal(candidate.id)

        assert evaluation.decision == "REJECTED"
        check = next(c for c in evaluation.checks if c["name"] == "max_concurrent_positions")
        assert check["passed"] is False
    finally:
        await risk_service.update_policy(original)


@pytest.mark.asyncio
async def test_portfolio_exposure_rejects_when_over_the_limit(db_session) -> None:
    await _ensure_at_least_one_open_position(db_session, "NVDA")
    risk_service = _risk_service(db_session)
    original = await _capture_policy_values(db_session)
    updated = dict(original)
    # NUMERIC(5,2) — 0.01 is the smallest representable positive value.
    updated["max_portfolio_exposure_pct"] = Decimal("0.01")

    try:
        await risk_service.update_policy(updated)
        candidate = await _make_candidate_signal(db_session, "AMZN")
        evaluation = await risk_service.evaluate_signal(candidate.id)

        assert evaluation.decision == "REJECTED"
        check = next(c for c in evaluation.checks if c["name"] == "portfolio_exposure")
        assert check["passed"] is False
    finally:
        await risk_service.update_policy(original)


@pytest.mark.asyncio
async def test_daily_loss_limit_rejects_after_a_realized_loss_today(db_session) -> None:
    risk_service = _risk_service(db_session)
    original = await _capture_policy_values(db_session)
    updated = dict(original)
    updated["max_daily_loss_pct"] = Decimal("0.01")

    fill_id, original_cash = await _apply_synthetic_loss(
        db_session, Decimal("50.00"), datetime.now(UTC)
    )
    try:
        await risk_service.update_policy(updated)
        candidate = await _make_candidate_signal(db_session, "TSLA")
        evaluation = await risk_service.evaluate_signal(candidate.id)

        assert evaluation.decision == "REJECTED"
        check = next(c for c in evaluation.checks if c["name"] == "daily_loss_limit")
        assert check["passed"] is False
    finally:
        await risk_service.update_policy(original)
        await _undo_synthetic_loss(db_session, fill_id, original_cash)


@pytest.mark.asyncio
async def test_max_drawdown_rejects_after_equity_falls_from_its_peak(db_session) -> None:
    risk_service = _risk_service(db_session)
    original = await _capture_policy_values(db_session)
    updated = dict(original)
    updated["max_drawdown_pct"] = Decimal("0.01")

    # A large loss (bigger than the daily-loss test's) so the drawdown
    # is unambiguous regardless of the account's current equity.
    fill_id, original_cash = await _apply_synthetic_loss(
        db_session, Decimal("5000.00"), datetime.now(UTC)
    )
    try:
        await risk_service.update_policy(updated)
        candidate = await _make_candidate_signal(db_session, "AAPL")
        evaluation = await risk_service.evaluate_signal(candidate.id)

        assert evaluation.decision == "REJECTED"
        check = next(c for c in evaluation.checks if c["name"] == "max_drawdown")
        assert check["passed"] is False
    finally:
        await risk_service.update_policy(original)
        await _undo_synthetic_loss(db_session, fill_id, original_cash)


@pytest.mark.asyncio
async def test_loss_cooldown_rejects_immediately_after_a_losing_trade(db_session) -> None:
    risk_service = _risk_service(db_session)
    original = await _capture_policy_values(db_session)
    updated = dict(original)
    updated["cooldown_after_loss_minutes"] = 10080  # 7 days — the CHECK constraint's max

    fill_id, original_cash = await _apply_synthetic_loss(
        db_session, Decimal("10.00"), datetime.now(UTC)
    )
    try:
        await risk_service.update_policy(updated)
        candidate = await _make_candidate_signal(db_session, "MSFT")
        evaluation = await risk_service.evaluate_signal(candidate.id)

        assert evaluation.decision == "REJECTED"
        check = next(c for c in evaluation.checks if c["name"] == "loss_cooldown")
        assert check["passed"] is False
    finally:
        await risk_service.update_policy(original)
        await _undo_synthetic_loss(db_session, fill_id, original_cash)
