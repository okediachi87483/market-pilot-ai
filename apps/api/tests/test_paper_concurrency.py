"""Concurrency tests: two genuinely simultaneous requests against the
same mutable state, using two independent AsyncSessions (never a single
shared session across coroutines) — a real reproduction of "what
happens if two requests race," not just a sequential before/after
check. Requires a live Postgres — auto-skipped otherwise (see
tests/conftest.py db_engine).
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ConflictError
from app.models.asset import Asset
from app.models.paper_trading import PaperOrder
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.paper_trading.execution import PaperExecutionAdapter
from app.services.paper_trading.service import PaperTradingService

FEE_RATE = Decimal("0.001")


def _service(session) -> PaperTradingService:
    market_data = MarketDataService(session)
    execution_adapter = PaperExecutionAdapter(market_data, FEE_RATE)
    return PaperTradingService(session, execution_adapter, market_data)


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
        reasons=["concurrency test fixture"],
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
        entry_price=Decimal("100"),
        stop_loss_price=Decimal("98"),
        take_profit_price=Decimal("104"),
        position_value=quantity * Decimal("100"),
        portfolio_snapshot={},
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


@pytest.mark.asyncio
async def test_concurrent_execute_signal_for_the_same_signal_creates_exactly_one_order(
    db_engine, db_session
) -> None:
    """Two requests racing to execute the same RISK_APPROVED signal at
    the same instant — a real concurrency scenario, not a sequential
    before/after call. `paper_orders.signal_id` is UNIQUE at the
    database level (docs/paper-trading.md §15), so exactly one insert
    can ever land; the other must fail cleanly as a 409 ConflictError,
    never an unhandled exception."""
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def attempt() -> PaperOrder | Exception:
        async with session_factory() as session:
            service = _service(session)
            try:
                return await service.execute_signal(signal.id)
            except Exception as exc:  # noqa: BLE001 — capturing to assert on below
                return exc

    result_a, result_b = await asyncio.gather(attempt(), attempt(), return_exceptions=False)
    results = [result_a, result_b]

    orders = [r for r in results if isinstance(r, PaperOrder)]
    errors = [r for r in results if isinstance(r, Exception)]

    assert len(orders) == 1, "exactly one of the two concurrent attempts must create the order"
    assert len(errors) == 1, "the other attempt must fail, not silently succeed a second time"
    assert isinstance(errors[0], ConflictError), (
        f"the losing concurrent attempt must surface as a clean 409 ConflictError, "
        f"not {type(errors[0]).__name__}: {errors[0]}"
    )

    # And the database itself agrees: exactly one order for this signal.
    verify_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with verify_session_factory() as verify_session:
        rows = (
            (
                await verify_session.execute(
                    select(PaperOrder).where(PaperOrder.signal_id == signal.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_concurrent_close_position_for_the_same_symbol_closes_exactly_once(
    db_engine, db_session
) -> None:
    """Open a position, then race two concurrent close requests against
    it. Only one may actually sell the position; the other must find no
    open position left (404), never double-sell or create a negative
    quantity."""
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("2"))
    service = _service(db_session)
    await service.execute_signal(signal.id)

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def attempt_close() -> PaperOrder | Exception:
        async with session_factory() as session:
            svc = _service(session)
            try:
                return await svc.close_position("MSFT")
            except Exception as exc:  # noqa: BLE001
                return exc

    result_a, result_b = await asyncio.gather(attempt_close(), attempt_close())
    results = [result_a, result_b]

    orders = [r for r in results if isinstance(r, PaperOrder)]
    errors = [r for r in results if isinstance(r, Exception)]

    assert len(orders) == 1, "exactly one of the two concurrent closes must succeed"
    assert len(errors) == 1
    # Whichever loses must fail cleanly, not corrupt state — a 404 (no
    # position left) or 409 (nothing left to sell) are both acceptable
    # honest outcomes; an unhandled exception is not.
    from app.core.errors import AppError

    assert isinstance(errors[0], AppError), (
        f"the losing concurrent close must surface as a clean AppError, "
        f"not {type(errors[0]).__name__}: {errors[0]}"
    )


@pytest.mark.asyncio
async def test_concurrent_buy_racing_a_close_never_loses_or_fabricates_shares(
    db_engine, db_session
) -> None:
    """A BUY that adds to a position, racing a close of that same
    position — the scenario the quantity-mismatch check in
    close_position() exists for (docs/paper-trading.md concurrency
    note). Whichever order the two operations actually land in, the
    books must always balance: every share this test buys is either
    still open or was sold — none can silently vanish (which is exactly
    what a stale identity-mapped read would cause: close_position
    computing against a cached pre-race quantity instead of the real
    one).

    `paper_fills`/`paper_positions` are shared across the whole test
    suite (test_paper_service.py's own module docstring), and NVDA is a
    commonly-reused fixture symbol, so this asserts on *before/after
    deltas* for exactly the shares this test itself creates — never an
    absolute count — the same discipline every other test in this
    package already follows."""
    from app.models.paper_trading import PaperFill
    from app.services.paper_trading.service import PaperTradingService

    async def _nvda_totals(session) -> tuple[Decimal, Decimal, Decimal]:
        svc = PaperTradingService(
            session,
            PaperExecutionAdapter(MarketDataService(session), FEE_RATE),
            MarketDataService(session),
        )
        asset_result = await session.execute(select(Asset).where(Asset.symbol == "NVDA"))
        asset = asset_result.scalar_one()
        fills = (
            (await session.execute(select(PaperFill).where(PaperFill.asset_id == asset.id)))
            .scalars()
            .all()
        )
        bought = sum((f.quantity for f in fills if f.side == "BUY"), Decimal("0"))
        sold = sum((f.quantity for f in fills if f.side == "SELL"), Decimal("0"))
        open_positions = await svc.list_positions(status="OPEN")
        still_open = sum(
            (p.quantity for p in open_positions if p.asset_id == asset.id), Decimal("0")
        )
        return bought, sold, still_open

    bought_before, sold_before, open_before = await _nvda_totals(db_session)

    opening_signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("2"))
    opener = _service(db_session)
    await opener.execute_signal(opening_signal.id)

    adding_signal = await _make_risk_approved_signal(db_session, "NVDA", Decimal("1"))

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def do_buy() -> PaperOrder | Exception:
        async with session_factory() as session:
            svc = _service(session)
            try:
                return await svc.execute_signal(adding_signal.id)
            except Exception as exc:  # noqa: BLE001
                return exc

    async def do_close() -> PaperOrder | Exception:
        async with session_factory() as session:
            svc = _service(session)
            try:
                return await svc.close_position("NVDA")
            except Exception as exc:  # noqa: BLE001
                return exc

    buy_result, close_result = await asyncio.gather(do_buy(), do_close())

    # The close may legitimately lose the race with a clean ConflictError
    # (asking the caller to retry) rather than proceed against stale
    # data — that is a correct, honest outcome, not a bug.
    for result in (buy_result, close_result):
        if isinstance(result, Exception):
            assert isinstance(
                result, ConflictError
            ), f"a losing side must fail cleanly, not {type(result).__name__}: {result}"

    verify_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with verify_session_factory() as verify_session:
        bought_after, sold_after, open_after = await _nvda_totals(verify_session)

    bought_delta = bought_after - bought_before
    sold_delta = sold_after - sold_before
    open_delta = open_after - open_before

    # Conservation of shares: nothing this test buys can silently
    # disappear — it is either still held or was actually sold.
    assert bought_delta == sold_delta + open_delta, (
        f"share conservation violated: bought_delta={bought_delta} "
        f"sold_delta={sold_delta} open_delta={open_delta} "
        f"(bought_delta must equal sold_delta + open_delta)"
    )
    # And this test bought exactly 2 (opening) + 1 (adding) = 3 shares —
    # confirms the delta accounting itself is wired correctly.
    assert bought_delta == Decimal("3")
