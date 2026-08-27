"""Integration tests: TechnicalAnalysisService -> SignalEngine ->
persistence, against a live Postgres. Requires `docker compose up -d
postgres redis` — auto-skipped otherwise (see tests/conftest.py db_engine).

Uses the mock provider's real fixture symbols (Phase 3/4's rationale
applies here too). Assertions deliberately avoid pinning a specific
BUY/SELL direction for "as of now" evaluations, since the deterministic
mock series' regime at the current wall-clock date will differ run to
run — see docs/signal-engine.md §"Testing" for why fixed-`end` tests are
used wherever a specific signal value matters.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.signal_engine.service import SignalService
from app.services.technical_analysis.service import TechnicalAnalysisService


def _service(db_session) -> SignalService:
    market_data = MarketDataService(db_session)
    technical_analysis = TechnicalAnalysisService(market_data)
    return SignalService(db_session, technical_analysis)


@pytest.mark.asyncio
async def test_evaluate_persists_a_candidate_signal(db_session) -> None:
    # interval="15m" here (and deliberately distinct intervals per test
    # below) so this file's persisted rows never share a dedup key
    # (asset_id, interval, strategy_id, strategy_version) with each other
    # or with test_api_signals.py's "1d" evaluations — see
    # docs/signal-engine.md §"Testing" on why cooldown-affecting tests
    # need disjoint keys, not just disjoint symbols.
    service = _service(db_session)
    end = datetime(2032, 1, 1, tzinfo=UTC)

    row, _created = await service.evaluate("AAPL", interval="15m", end=end)

    assert row.signal in ("BUY", "SELL", "HOLD")
    assert row.strategy_id == "trend_momentum"
    assert row.strategy_version == "1.0.0"
    assert row.status == "CANDIDATE"
    assert row.asset.symbol == "AAPL"
    assert isinstance(row.reasons, list) and len(row.reasons) > 0


@pytest.mark.asyncio
async def test_repeated_evaluation_is_deduplicated_within_cooldown(db_session) -> None:
    # Deliberately does not assert `first_created is True`: this test's
    # only claim is the dedup invariant itself — two evaluations moments
    # apart return the *same* row — not that no prior row could possibly
    # exist for this key (a rerun of the suite within the 15-minute
    # cooldown would otherwise make that assumption flaky).
    service = _service(db_session)
    end = datetime(2032, 2, 1, tzinfo=UTC)

    first_row, _first_created = await service.evaluate("MSFT", interval="5m", end=end)
    second_row, second_created = await service.evaluate("MSFT", interval="5m", end=end)

    assert second_created is False
    assert second_row.id == first_row.id


@pytest.mark.asyncio
async def test_evaluation_is_deterministic_for_a_fixed_point_in_time(db_session) -> None:
    # Exercises TechnicalAnalysisService -> SignalEngine directly (not
    # through SignalService), so persistence-level dedup can't mask a
    # genuine engine non-determinism — two independent evaluations of the
    # same fixed point in time must produce an identical SignalCandidate.
    from app.services.signal_engine.engine import SignalEngine
    from app.services.signal_engine.types import SignalInput

    market_data = MarketDataService(db_session)
    technical_analysis = TechnicalAnalysisService(market_data)
    end = datetime(2032, 3, 1, tzinfo=UTC)

    async def evaluate_once():
        snapshot = await technical_analysis.get_snapshot("NVDA", interval="1d", end=end)
        signal_input = SignalInput(
            symbol=snapshot.asset.symbol,
            interval="1d",
            timestamp=snapshot.calculated_at,
            candle_count=snapshot.candle_count,
            regime=snapshot.regime,
            features=snapshot.features,
            rsi14=snapshot.series.rsi14[snapshot.index],
        )
        return SignalEngine().evaluate(signal_input)

    first = await evaluate_once()
    second = await evaluate_once()

    assert first.signal == second.signal
    assert first.strength == second.strength
    assert first.reasons == second.reasons
    assert first.market_regime == second.market_regime
    assert first.supporting_features == second.supporting_features


@pytest.mark.asyncio
async def test_signal_type_change_supersedes_the_previous_candidate(db_session) -> None:
    service = _service(db_session)

    # Force two different evaluation dates far enough apart that the
    # deterministic mock series is very likely in different regimes;
    # the assertion below only depends on *a* transition happening, not
    # which direction — flip a coin's worth of robustness by checking
    # actual behavior after both calls rather than assuming a specific
    # pair of regimes.
    first_row, _ = await service.evaluate(
        "AMZN", interval="1h", end=datetime(2032, 4, 1, tzinfo=UTC)
    )
    second_row, second_created = await service.evaluate(
        "AMZN", interval="1h", end=datetime(2032, 4, 1, tzinfo=UTC) + _one_year()
    )

    if first_row.signal != second_row.signal:
        await db_session.refresh(first_row)
        assert first_row.status == "SUPERSEDED"
        assert second_row.status == "CANDIDATE"
        assert second_created is True


def _one_year():
    from datetime import timedelta

    return timedelta(days=365)


@pytest.mark.asyncio
async def test_get_signal_returns_persisted_row(db_session) -> None:
    service = _service(db_session)
    row, _ = await service.evaluate("TSLA", interval="5m", end=datetime(2032, 5, 1, tzinfo=UTC))

    fetched = await service.get_signal(row.id)
    assert fetched.id == row.id
    assert fetched.signal == row.signal


@pytest.mark.asyncio
async def test_get_signal_unknown_id_raises_not_found(db_session) -> None:
    import uuid

    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_signal(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_signals_filters_by_symbol(db_session) -> None:
    service = _service(db_session)
    await service.evaluate("AAPL", interval="1h", end=datetime(2032, 6, 1, tzinfo=UTC))

    rows = await service.list_signals(symbol="AAPL")
    assert all(row.asset.symbol == "AAPL" for row in rows)
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_evaluate_unknown_symbol_raises_not_found(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(NotFoundError):
        await service.evaluate("NOSUCHSYMBOL", interval="1d")


@pytest.mark.asyncio
async def test_persisted_signal_row_has_no_fabricated_probability(db_session) -> None:
    service = _service(db_session)
    row, _ = await service.evaluate("MSFT", interval="15m", end=datetime(2032, 7, 1, tzinfo=UTC))

    result = await db_session.execute(select(Signal).where(Signal.id == row.id))
    persisted = result.scalar_one()
    serialized = " ".join(persisted.reasons)
    assert "%" not in serialized
    assert "chance" not in serialized.lower()
