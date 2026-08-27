from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from app.services.market_data.normalizer import normalize_bar
from app.services.market_data.provider import ProviderBar


def _bar(**overrides) -> ProviderBar:
    from dataclasses import replace

    bar = ProviderBar(
        symbol="aapl",
        timestamp=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        open=Decimal("190.123456789"),
        high=Decimal("192"),
        low=Decimal("189"),
        close=Decimal("191"),
        volume=Decimal("1000000.123456789012"),
        interval="1D",
        source="Mock",
    )
    return replace(bar, **overrides)


def test_symbol_is_uppercased_and_stripped() -> None:
    normalized = normalize_bar(_bar(symbol="  aapl  "))
    assert normalized.symbol == "AAPL"


def test_interval_is_lowercased() -> None:
    normalized = normalize_bar(_bar(interval="1D"))
    assert normalized.interval == "1d"


def test_source_is_lowercased() -> None:
    normalized = normalize_bar(_bar(source="Mock"))
    assert normalized.source == "mock"


def test_price_is_quantized_to_eight_decimal_places() -> None:
    normalized = normalize_bar(_bar(open=Decimal("190.123456789")))
    assert normalized.open == Decimal("190.12345679")
    assert normalized.open.as_tuple().exponent == -8


def test_volume_is_quantized_to_ten_decimal_places() -> None:
    normalized = normalize_bar(_bar(volume=Decimal("1000000.123456789012")))
    assert normalized.volume.as_tuple().exponent == -10


def test_timestamp_already_utc_is_unchanged() -> None:
    ts = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    normalized = normalize_bar(_bar(timestamp=ts))
    assert normalized.timestamp == ts
    assert normalized.timestamp.tzinfo == UTC


def test_timestamp_in_another_timezone_is_converted_to_utc() -> None:
    est = timezone(timedelta(hours=-5))
    ts = datetime(2024, 6, 1, 8, 0, tzinfo=est)  # 13:00 UTC
    normalized = normalize_bar(_bar(timestamp=ts))
    assert normalized.timestamp == datetime(2024, 6, 1, 13, 0, tzinfo=UTC)
    assert normalized.timestamp.tzinfo == UTC


def test_normalization_does_not_change_ohlc_relationships() -> None:
    original = _bar()
    normalized = normalize_bar(original)
    assert normalized.high >= normalized.open
    assert normalized.high >= normalized.close
    assert normalized.low <= normalized.open
    assert normalized.low <= normalized.close
