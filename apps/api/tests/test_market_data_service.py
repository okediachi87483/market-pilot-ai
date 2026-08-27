"""Integration tests: provider -> validation -> normalization ->
persistence, against a live Postgres. Requires `docker compose up -d
postgres` — auto-skipped otherwise (see tests/conftest.py db_engine).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import NotFoundError, ValidationAppError
from app.models.asset import Asset
from app.services.market_data.provider import ProviderBar
from app.services.market_data.service import MarketDataService
from tests.conftest import unique_symbol


class _AlwaysInvalidProvider:
    """A stub provider whose bars always fail validation (high < open) —
    used to test the service's accept/reject wiring in isolation from the
    real mock provider, which is designed to always be valid. Accepts any
    symbol (it doesn't model a fixed fixture set the way MockMarketDataProvider
    does)."""

    def supported_symbols(self) -> list[str]:
        return []

    def get_quote(self, symbol: str, *, as_of: datetime) -> ProviderBar:
        return self.get_history(symbol, start=as_of, end=as_of, interval="1m")[0]

    def get_history(
        self, symbol: str, *, start: datetime, end: datetime, interval: str
    ) -> list[ProviderBar]:
        return [
            ProviderBar(
                symbol=symbol,
                timestamp=start,
                open=Decimal("100"),
                high=Decimal("50"),  # invalid: high < open
                low=Decimal("40"),
                close=Decimal("90"),
                volume=Decimal("1000"),
                interval=interval,
                source="mock",
            )
        ]


async def _create_asset(db_session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Test Co.", asset_type="equity", currency="USD")
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


@pytest.mark.asyncio
async def test_ingest_persists_accepted_bars(db_session) -> None:
    # AAPL is one of the mock provider's fixture symbols — see
    # app/services/market_data/mock_provider.py. Ephemeral test-only
    # symbols aren't recognized by it, so provider-backed tests use the
    # real seeded fixtures rather than unique_symbol().
    service = MarketDataService(db_session)

    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 6, 2, tzinfo=UTC)
    result = await service.ingest("AAPL", interval="1d", start=start, end=end)

    assert result.requested == result.accepted
    assert result.rejected == 0


@pytest.mark.asyncio
async def test_ingest_rejects_invalid_bars_without_persisting_them(db_session) -> None:
    symbol = unique_symbol("BADCO")
    asset = Asset(symbol=symbol, name="Bad Co.", asset_type="equity", currency="USD")
    db_session.add(asset)
    await db_session.commit()

    service = MarketDataService(db_session, provider=_AlwaysInvalidProvider())
    start = datetime(2024, 6, 1, tzinfo=UTC)
    result = await service.ingest(symbol, interval="1m", start=start, end=start)

    assert result.accepted == 0
    assert result.rejected == 1
    assert any("high" in reason for reason in result.rejected_reasons)


@pytest.mark.asyncio
async def test_get_quote_returns_persisted_bar(db_session) -> None:
    service = MarketDataService(db_session)

    asset, bar = await service.get_quote("MSFT", as_of=datetime(2024, 6, 1, tzinfo=UTC))

    assert asset.symbol == "MSFT"
    assert bar.interval == "1m"
    assert bar.source == "mock"
    assert bar.open > 0


@pytest.mark.asyncio
async def test_get_history_returns_bars_in_range(db_session) -> None:
    service = MarketDataService(db_session)

    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 6, 1, 6, 0, tzinfo=UTC)
    asset, rows = await service.get_history("NVDA", interval="1h", start=start, end=end)

    assert asset.symbol == "NVDA"
    assert len(rows) == 7  # inclusive hourly boundaries 00:00..06:00
    assert all(start <= row.timestamp <= end for row in rows)
    assert [row.timestamp for row in rows] == sorted(row.timestamp for row in rows)


@pytest.mark.asyncio
async def test_unknown_symbol_raises_not_found(db_session) -> None:
    service = MarketDataService(db_session)
    with pytest.raises(NotFoundError):
        await service.get_quote("NOSUCHSYMBOL")


@pytest.mark.asyncio
async def test_invalid_interval_raises_validation_error(db_session) -> None:
    service = MarketDataService(db_session)

    with pytest.raises(ValidationAppError):
        await service.ingest(
            "AAPL",
            interval="3d",
            start=datetime(2024, 6, 1, tzinfo=UTC),
            end=datetime(2024, 6, 2, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_start_after_end_raises_validation_error(db_session) -> None:
    service = MarketDataService(db_session)

    with pytest.raises(ValidationAppError):
        await service.ingest(
            "AAPL",
            interval="1d",
            start=datetime(2024, 6, 5, tzinfo=UTC),
            end=datetime(2024, 6, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_list_assets_only_returns_active_by_default(db_session) -> None:
    symbol = unique_symbol()
    asset = Asset(
        symbol=symbol, name="Inactive Co.", asset_type="equity", currency="USD", active=False
    )
    db_session.add(asset)
    await db_session.commit()

    service = MarketDataService(db_session)
    assets = await service.list_assets()

    assert symbol not in {a.symbol for a in assets}


@pytest.mark.asyncio
async def test_asset_lookup_is_case_insensitive(db_session) -> None:
    symbol = unique_symbol()
    await _create_asset(db_session, symbol)
    service = MarketDataService(db_session)

    found = await service.get_asset(symbol.lower())
    assert found.symbol == symbol
