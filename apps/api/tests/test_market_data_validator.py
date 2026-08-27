from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from app.services.market_data.provider import ProviderBar
from app.services.market_data.validator import is_valid, validate_bar


def _valid_bar(**overrides) -> ProviderBar:
    bar = ProviderBar(
        symbol="AAPL",
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        open=Decimal("190.00"),
        high=Decimal("192.00"),
        low=Decimal("189.00"),
        close=Decimal("191.00"),
        volume=Decimal("1000000"),
        interval="1d",
        source="mock",
    )
    return replace(bar, **overrides)


def test_valid_bar_has_no_errors() -> None:
    assert validate_bar(_valid_bar()) == []
    assert is_valid(_valid_bar())


def test_high_below_open_is_rejected() -> None:
    bar = _valid_bar(high=Decimal("189.50"))
    errors = validate_bar(bar)
    assert any("high" in e and "open" in e for e in errors)


def test_high_below_close_is_rejected() -> None:
    bar = _valid_bar(high=Decimal("190.50"), close=Decimal("191.00"))
    errors = validate_bar(bar)
    assert any("high" in e and "close" in e for e in errors)


def test_high_below_low_is_rejected() -> None:
    bar = _valid_bar(high=Decimal("188.00"), low=Decimal("189.00"))
    errors = validate_bar(bar)
    assert any("high" in e and "low" in e for e in errors)


def test_low_above_open_is_rejected() -> None:
    bar = _valid_bar(low=Decimal("190.50"))
    errors = validate_bar(bar)
    assert any("low" in e and "open" in e for e in errors)


def test_low_above_close_is_rejected() -> None:
    bar = _valid_bar(low=Decimal("191.50"), open=Decimal("192.00"))
    errors = validate_bar(bar)
    assert any("low" in e and "close" in e for e in errors)


def test_negative_volume_is_rejected() -> None:
    bar = _valid_bar(volume=Decimal("-1"))
    errors = validate_bar(bar)
    assert any("volume" in e for e in errors)


def test_zero_volume_is_valid() -> None:
    # volume >= 0, so exactly zero (a bar with no trades) is legitimate.
    assert validate_bar(_valid_bar(volume=Decimal("0"))) == []


def test_non_positive_prices_are_rejected() -> None:
    for field in ("open", "high", "low", "close"):
        bar = _valid_bar(**{field: Decimal("0")})
        errors = validate_bar(bar)
        assert any(field in e for e in errors), f"{field}=0 should be rejected"


def test_naive_timestamp_is_rejected() -> None:
    bar = _valid_bar(timestamp=datetime(2024, 6, 1))  # no tzinfo
    errors = validate_bar(bar)
    assert any("timestamp" in e for e in errors)


def test_unsupported_interval_is_rejected() -> None:
    bar = _valid_bar(interval="3d")
    errors = validate_bar(bar)
    assert any("interval" in e for e in errors)


def test_malformed_symbol_is_rejected() -> None:
    bar = _valid_bar(symbol="")
    errors = validate_bar(bar)
    assert any("symbol" in e for e in errors)


def test_multiple_violations_are_all_reported() -> None:
    bar = _valid_bar(volume=Decimal("-5"), interval="bogus")
    errors = validate_bar(bar)
    assert len(errors) >= 2
