"""Database-layer tests: persistence and idempotent ingestion. Requires
a live Postgres (see tests/conftest.py db_engine) — auto-skipped otherwise.

Uses the mock provider's real fixture symbols (AAPL/MSFT/NVDA/AMZN/TSLA)
rather than synthetic test symbols, since MockMarketDataProvider only
serves that fixed set. Each test scopes its row-count assertions to its
own (asset, interval, timestamp range) rather than counting all rows for
the asset, so tests remain correct however many times the suite has run
before against this database — idempotent ingestion means re-running a
test's own range never inflates its count, but a shared symbol can
legitimately carry other tests' data outside that range.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.asset import Asset
from app.models.market_data import MarketData
from app.services.market_data.service import MarketDataService


async def _get_asset(db_session, symbol: str) -> Asset:
    result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    return result.scalar_one()


async def _row_count(db_session, asset_id, *, interval: str, start: datetime, end: datetime) -> int:
    result = await db_session.execute(
        select(func.count())
        .select_from(MarketData)
        .where(
            MarketData.asset_id == asset_id,
            MarketData.interval == interval,
            MarketData.timestamp >= start,
            MarketData.timestamp <= end,
        )
    )
    return int(result.scalar_one())


@pytest.mark.asyncio
async def test_ingested_bars_are_persisted_to_postgres(db_session) -> None:
    asset = await _get_asset(db_session, "AAPL")
    service = MarketDataService(db_session)

    start = datetime(2031, 1, 1, tzinfo=UTC)
    end = datetime(2031, 1, 1, 5, 0, tzinfo=UTC)
    result = await service.ingest("AAPL", interval="1h", start=start, end=end)

    assert result.accepted == 6
    assert await _row_count(db_session, asset.id, interval="1h", start=start, end=end) == 6


@pytest.mark.asyncio
async def test_reingesting_the_same_range_does_not_create_duplicates(db_session) -> None:
    asset = await _get_asset(db_session, "MSFT")
    service = MarketDataService(db_session)

    start = datetime(2031, 2, 1, tzinfo=UTC)
    end = datetime(2031, 2, 1, 5, 0, tzinfo=UTC)

    await service.ingest("MSFT", interval="1h", start=start, end=end)
    first_count = await _row_count(db_session, asset.id, interval="1h", start=start, end=end)

    # Re-ingest the identical range twice more.
    await service.ingest("MSFT", interval="1h", start=start, end=end)
    await service.ingest("MSFT", interval="1h", start=start, end=end)
    final_count = await _row_count(db_session, asset.id, interval="1h", start=start, end=end)

    assert first_count == 6
    assert final_count == first_count


@pytest.mark.asyncio
async def test_overlapping_ingest_only_adds_new_bars(db_session) -> None:
    asset = await _get_asset(db_session, "NVDA")
    service = MarketDataService(db_session)

    window_start = datetime(2031, 3, 1, 0, 0, tzinfo=UTC)
    midpoint = datetime(2031, 3, 1, 3, 0, tzinfo=UTC)
    window_end = datetime(2031, 3, 1, 6, 0, tzinfo=UTC)

    await service.ingest("NVDA", interval="1h", start=window_start, end=midpoint)
    first_count = await _row_count(
        db_session, asset.id, interval="1h", start=window_start, end=midpoint
    )
    assert first_count == 4

    # Overlaps the first 4 hours and extends 3 hours further.
    overlap_start = datetime(2031, 3, 1, 1, 0, tzinfo=UTC)
    await service.ingest("NVDA", interval="1h", start=overlap_start, end=window_end)
    final_count = await _row_count(
        db_session, asset.id, interval="1h", start=window_start, end=window_end
    )
    assert final_count == 7


@pytest.mark.asyncio
async def test_same_timestamp_different_interval_is_not_a_duplicate(db_session) -> None:
    asset = await _get_asset(db_session, "AMZN")
    service = MarketDataService(db_session)

    ts = datetime(2031, 4, 1, tzinfo=UTC)
    await service.ingest("AMZN", interval="1h", start=ts, end=ts)
    await service.ingest("AMZN", interval="1d", start=ts, end=ts)

    hourly = await _row_count(db_session, asset.id, interval="1h", start=ts, end=ts)
    daily = await _row_count(db_session, asset.id, interval="1d", start=ts, end=ts)
    assert hourly == 1
    assert daily == 1


@pytest.mark.asyncio
async def test_persisted_rows_use_decimal_not_float(db_session) -> None:
    asset = await _get_asset(db_session, "TSLA")
    service = MarketDataService(db_session)

    ts = datetime(2031, 5, 1, tzinfo=UTC)
    await service.ingest("TSLA", interval="1d", start=ts, end=ts)

    result = await db_session.execute(
        select(MarketData)
        .where(
            MarketData.asset_id == asset.id,
            MarketData.interval == "1d",
            MarketData.timestamp == ts,
        )
        .limit(1)
    )
    row = result.scalar_one()

    assert isinstance(row.open, Decimal)
    assert isinstance(row.volume, Decimal)
