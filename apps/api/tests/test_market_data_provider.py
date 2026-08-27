from datetime import UTC, datetime

import pytest

from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.market_data.provider import SymbolNotSupportedError


@pytest.fixture
def provider() -> MockMarketDataProvider:
    return MockMarketDataProvider()


def test_supported_symbols_includes_fixture_set(provider: MockMarketDataProvider) -> None:
    symbols = provider.supported_symbols()
    assert set(symbols) == {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}


def test_get_quote_is_deterministic(provider: MockMarketDataProvider) -> None:
    as_of = datetime(2024, 6, 1, 15, 30, tzinfo=UTC)
    first = provider.get_quote("AAPL", as_of=as_of)
    second = provider.get_quote("AAPL", as_of=as_of)
    assert first == second


def test_get_history_is_deterministic(provider: MockMarketDataProvider) -> None:
    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 6, 2, tzinfo=UTC)
    first = provider.get_history("NVDA", start=start, end=end, interval="1h")
    second = provider.get_history("NVDA", start=start, end=end, interval="1h")
    assert first == second
    assert len(first) > 0


def test_get_history_bars_are_internally_consistent(provider: MockMarketDataProvider) -> None:
    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 6, 3, tzinfo=UTC)
    bars = provider.get_history("TSLA", start=start, end=end, interval="1d")
    assert len(bars) > 0
    for bar in bars:
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.high >= bar.low
        assert bar.low <= bar.open
        assert bar.low <= bar.close
        assert bar.open > 0
        assert bar.volume >= 0
        assert bar.source == "mock"
        assert bar.interval == "1d"


def test_get_history_respects_requested_interval_count(provider: MockMarketDataProvider) -> None:
    start = datetime(2024, 6, 1, 0, 0, tzinfo=UTC)
    end = datetime(2024, 6, 1, 1, 0, tzinfo=UTC)
    bars = provider.get_history("AAPL", start=start, end=end, interval="1m")
    # 61 one-minute boundaries fall in a closed [00:00, 01:00] window.
    assert len(bars) == 61


def test_unknown_symbol_raises(provider: MockMarketDataProvider) -> None:
    with pytest.raises(SymbolNotSupportedError):
        provider.get_quote("ZZZZ", as_of=datetime.now(UTC))

    with pytest.raises(SymbolNotSupportedError):
        provider.get_history("ZZZZ", start=datetime.now(UTC), end=datetime.now(UTC), interval="1d")


def test_different_symbols_produce_different_series(provider: MockMarketDataProvider) -> None:
    as_of = datetime(2024, 6, 1, tzinfo=UTC)
    aapl = provider.get_quote("AAPL", as_of=as_of)
    msft = provider.get_quote("MSFT", as_of=as_of)
    assert aapl.close != msft.close
