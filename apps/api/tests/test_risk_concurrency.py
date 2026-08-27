"""Concurrency tests: two genuinely simultaneous requests against the
same CANDIDATE signal, using two independent AsyncSessions (never a
single shared session across coroutines). Requires a live Postgres —
auto-skipped otherwise (see tests/conftest.py db_engine).
"""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ConflictError
from app.models.asset import Asset
from app.models.risk import RiskEvaluation
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.risk_engine.portfolio_state import PortfolioStateProvider
from app.services.risk_engine.service import RiskService


def _service(session) -> RiskService:
    market_data = MarketDataService(session)
    portfolio_state_provider = PortfolioStateProvider(session, market_data)
    return RiskService(session, market_data, portfolio_state_provider)


async def _make_candidate_signal(db_session, symbol: str, signal_type: str) -> Signal:
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
        reasons=["concurrency test fixture"],
        supporting_features={"rsi14": 55.0},
        invalidating_conditions=[],
        status="CANDIDATE",
        generated_at=datetime.now(UTC),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_concurrent_evaluate_signal_for_the_same_signal_creates_exactly_one_evaluation(
    db_engine, db_session
) -> None:
    """Two requests racing to risk-evaluate the same CANDIDATE signal at
    the same instant. Unlike paper_orders.signal_id, RiskEvaluation has
    no unique constraint on signal_id — nothing at the database level
    prevents two evaluations from being created unless the service
    itself serializes the check-then-transition sequence. Exactly one
    evaluation must be created, and the signal's final status must match
    that one evaluation's decision, never a corrupted/overwritten state."""
    signal = await _make_candidate_signal(db_session, "AAPL", "BUY")
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def attempt() -> RiskEvaluation | Exception:
        async with session_factory() as session:
            service = _service(session)
            try:
                return await service.evaluate_signal(signal.id)
            except Exception as exc:  # noqa: BLE001
                return exc

    result_a, result_b = await asyncio.gather(attempt(), attempt())
    results = [result_a, result_b]

    evaluations = [r for r in results if isinstance(r, RiskEvaluation)]
    errors = [r for r in results if isinstance(r, Exception)]

    assert len(evaluations) == 1, "exactly one of the two concurrent attempts must evaluate"
    assert len(errors) == 1, "the other attempt must fail, not silently evaluate a second time"
    assert isinstance(errors[0], ConflictError), (
        f"the losing concurrent attempt must surface as a clean 409 ConflictError, "
        f"not {type(errors[0]).__name__}: {errors[0]}"
    )

    verify_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with verify_session_factory() as verify_session:
        rows = (
            (
                await verify_session.execute(
                    select(RiskEvaluation).where(RiskEvaluation.signal_id == signal.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "the database must never end up with two evaluations for one signal"

        refreshed_signal = (
            await verify_session.execute(select(Signal).where(Signal.id == signal.id))
        ).scalar_one()
        assert refreshed_signal.status in ("RISK_APPROVED", "RISK_REJECTED")
        expected_status = "RISK_APPROVED" if rows[0].decision == "APPROVED" else "RISK_REJECTED"
        assert refreshed_signal.status == expected_status


@pytest.mark.asyncio
async def test_concurrent_evaluate_different_signals_both_succeed_independently(
    db_engine, db_session
) -> None:
    """Sanity check: the signal-level lock must not over-serialize
    unrelated signals — two different CANDIDATE signals evaluated at the
    same time must both succeed."""
    signal_a = await _make_candidate_signal(db_session, "AAPL", "BUY")
    signal_b = await _make_candidate_signal(db_session, "MSFT", "BUY")
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def attempt(signal_id) -> RiskEvaluation | Exception:
        async with session_factory() as session:
            service = _service(session)
            try:
                return await service.evaluate_signal(signal_id)
            except Exception as exc:  # noqa: BLE001
                return exc

    result_a, result_b = await asyncio.gather(attempt(signal_a.id), attempt(signal_b.id))

    assert isinstance(result_a, RiskEvaluation), result_a
    assert isinstance(result_b, RiskEvaluation), result_b
    assert result_a.signal_id == signal_a.id
    assert result_b.signal_id == signal_b.id
