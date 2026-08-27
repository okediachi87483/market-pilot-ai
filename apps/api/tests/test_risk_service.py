"""Integration tests: RiskService against a live Postgres. Requires
`docker compose up -d postgres redis` — auto-skipped otherwise (see
tests/conftest.py db_engine).

The active `RiskPolicy` is a process-wide singleton (Step 4), so unlike
Phase 5's signal cooldown (isolated per `(symbol, interval)` key), tests
here cannot isolate themselves by picking a disjoint key — there is only
ever one active policy for the whole suite. `test_update_policy_...`
below is the only test that calls `update_policy()`; it captures the
original active values first and restores them at the end, so every
other test in the suite (this file and others, since Postgres state is
shared and not rolled back per test) always evaluates against the same
effective policy values regardless of run order.

Since Phase 7, `PortfolioStateProvider` reads *real* paper-trading state
(docs/risk-engine.md §4 was the Phase 6 placeholder; it's gone). That
means a test asserting "a healthy signal is approved" is no longer safe
on its own: a real loss realized by some other test (e.g. fees
exceeding a tiny gain on a close) can put the shared account into a
genuine loss-cooldown, which would correctly reject even a well-formed
candidate. `_neutralize_cooldown` below temporarily zeroes
`cooldown_after_loss_minutes` (capture-and-restore, same discipline as
`test_update_policy_...`) so that specific, unrelated risk stays from
interfering with a test that isn't about cooldown at all.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.risk_engine.portfolio_state import PortfolioStateProvider
from app.services.risk_engine.service import RiskService


def _service(db_session) -> RiskService:
    market_data = MarketDataService(db_session)
    portfolio_state_provider = PortfolioStateProvider(db_session, market_data)
    return RiskService(db_session, market_data, portfolio_state_provider)


@asynccontextmanager
async def _neutralize_cooldown(service: RiskService):
    """Temporarily zeroes `cooldown_after_loss_minutes` so a real loss
    realized elsewhere in the shared test session can't reject a signal
    this test expects to be approved for unrelated reasons — see the
    module docstring."""
    original = await service.get_active_policy()
    original_values = {
        "enabled": original.enabled,
        "max_position_size_pct": original.max_position_size_pct,
        "max_portfolio_exposure_pct": original.max_portfolio_exposure_pct,
        "max_daily_loss_pct": original.max_daily_loss_pct,
        "max_drawdown_pct": original.max_drawdown_pct,
        "stop_loss_pct": original.stop_loss_pct,
        "take_profit_pct": original.take_profit_pct,
        "risk_per_trade_pct": original.risk_per_trade_pct,
        "max_concurrent_positions": original.max_concurrent_positions,
        "cooldown_after_loss_minutes": original.cooldown_after_loss_minutes,
    }
    neutralized = dict(original_values)
    neutralized["cooldown_after_loss_minutes"] = 0
    try:
        await service.update_policy(neutralized)
        yield
    finally:
        await service.update_policy(original_values)


async def _make_signal(db_session, symbol: str, signal_type: str, *, status="CANDIDATE") -> Signal:
    result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalar_one()
    row = Signal(
        asset_id=asset.id,
        interval="1d",
        signal=signal_type,
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG" if signal_type in ("BUY", "SELL") else None,
        market_regime="BULLISH" if signal_type == "BUY" else "BEARISH",
        reasons=["test fixture signal"],
        supporting_features={"rsi14": 55.0},
        invalidating_conditions=[],
        status=status,
        generated_at=datetime.now(UTC),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_evaluate_healthy_buy_signal_is_approved_and_transitions_status(db_session) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY")
    service = _service(db_session)

    async with _neutralize_cooldown(service):
        evaluation = await service.evaluate_signal(signal.id)

        assert evaluation.decision == "APPROVED"
        assert evaluation.calculated_position_size is not None
        assert evaluation.calculated_position_size > 0
        assert evaluation.stop_loss_price is not None
        assert evaluation.take_profit_price is not None

        await db_session.refresh(signal)
        assert signal.status == "RISK_APPROVED"


@pytest.mark.asyncio
async def test_evaluate_sell_signal_is_rejected_and_transitions_status(db_session) -> None:
    signal = await _make_signal(db_session, "MSFT", "SELL")
    service = _service(db_session)

    evaluation = await service.evaluate_signal(signal.id)

    assert evaluation.decision == "REJECTED"
    assert len(evaluation.reasons) >= 1

    await db_session.refresh(signal)
    assert signal.status == "RISK_REJECTED"


@pytest.mark.asyncio
async def test_evaluate_hold_signal_is_rejected(db_session) -> None:
    signal = await _make_signal(db_session, "AAPL", "HOLD")
    service = _service(db_session)

    evaluation = await service.evaluate_signal(signal.id)

    assert evaluation.decision == "REJECTED"


@pytest.mark.asyncio
async def test_evaluating_an_already_evaluated_signal_raises_conflict(db_session) -> None:
    signal = await _make_signal(db_session, "TSLA", "BUY")
    service = _service(db_session)

    await service.evaluate_signal(signal.id)
    with pytest.raises(ConflictError):
        await service.evaluate_signal(signal.id)


@pytest.mark.asyncio
async def test_evaluating_a_non_candidate_signal_raises_conflict_without_evaluating(
    db_session,
) -> None:
    signal = await _make_signal(db_session, "AMZN", "BUY", status="SUPERSEDED")
    service = _service(db_session)

    with pytest.raises(ConflictError):
        await service.evaluate_signal(signal.id)

    await db_session.refresh(signal)
    assert signal.status == "SUPERSEDED"  # untouched


@pytest.mark.asyncio
async def test_evaluate_unknown_signal_raises_not_found(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.evaluate_signal(uuid.uuid4())


@pytest.mark.asyncio
async def test_evaluation_persists_the_complete_audit_trail(db_session) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY")
    service = _service(db_session)

    evaluation = await service.evaluate_signal(signal.id)
    fetched = await service.get_evaluation(evaluation.id)

    assert fetched.signal_id == signal.id
    assert fetched.policy_id is not None
    assert fetched.policy_version >= 1
    assert len(fetched.checks) == 11
    assert isinstance(fetched.portfolio_snapshot, dict)
    assert "equity" in fetched.portfolio_snapshot
    assert fetched.evaluated_at is not None


@pytest.mark.asyncio
async def test_get_evaluation_unknown_id_raises_not_found(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_evaluation(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_evaluations_filters_by_decision(db_session) -> None:
    approved_signal = await _make_signal(db_session, "AAPL", "BUY")
    rejected_signal = await _make_signal(db_session, "MSFT", "SELL")
    service = _service(db_session)
    await service.evaluate_signal(approved_signal.id)
    await service.evaluate_signal(rejected_signal.id)

    approved_rows = await service.list_evaluations(decision="APPROVED")
    rejected_rows = await service.list_evaluations(decision="REJECTED")

    assert all(row.decision == "APPROVED" for row in approved_rows)
    assert all(row.decision == "REJECTED" for row in rejected_rows)


@pytest.mark.asyncio
async def test_list_evaluations_filters_by_signal_id(db_session) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY")
    service = _service(db_session)
    evaluation = await service.evaluate_signal(signal.id)

    rows = await service.list_evaluations(signal_id=signal.id)

    assert len(rows) == 1
    assert rows[0].id == evaluation.id


@pytest.mark.asyncio
async def test_update_policy_creates_a_new_version_and_preserves_the_old_one(db_session) -> None:
    service = _service(db_session)
    original = await service.get_active_policy()
    original_values = {
        "enabled": original.enabled,
        "max_position_size_pct": original.max_position_size_pct,
        "max_portfolio_exposure_pct": original.max_portfolio_exposure_pct,
        "max_daily_loss_pct": original.max_daily_loss_pct,
        "max_drawdown_pct": original.max_drawdown_pct,
        "stop_loss_pct": original.stop_loss_pct,
        "take_profit_pct": original.take_profit_pct,
        "risk_per_trade_pct": original.risk_per_trade_pct,
        "max_concurrent_positions": original.max_concurrent_positions,
        "cooldown_after_loss_minutes": original.cooldown_after_loss_minutes,
    }
    original_id = original.id
    original_version = original.version

    changed_values = dict(original_values)
    changed_values["max_position_size_pct"] = (
        original_values["max_position_size_pct"] / 2
        if original_values["max_position_size_pct"] > 2
        else original_values["max_position_size_pct"]
    )

    try:
        updated = await service.update_policy(changed_values)
        assert updated.version == original_version + 1
        assert updated.is_active is True
        assert updated.max_position_size_pct == changed_values["max_position_size_pct"]

        active = await service.get_active_policy()
        assert active.id == updated.id

        result = await db_session.execute(
            select(type(original)).where(type(original).id == original_id)
        )
        original_row = result.scalar_one()
        assert original_row.is_active is False
    finally:
        # Restore the original values (as a new version) so every other
        # test in the suite evaluates against unchanged effective limits
        # regardless of run order — see module docstring.
        await service.update_policy(original_values)
        restored = await service.get_active_policy()
        assert restored.max_position_size_pct == original_values["max_position_size_pct"]
