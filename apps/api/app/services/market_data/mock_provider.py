"""Deterministic mock market data provider.

Development/testing fixture only — see docs/market-data.md. Prices are
computed in closed form from (symbol, interval, bar index), so the same
request always produces byte-identical output, and any individual bar can
be computed directly without replaying history from an anchor. This is
what makes ingestion idempotency testable: re-ingesting the same range
regenerates the same rows.

Every bar's `source` is "mock" — never presented as real market data
anywhere downstream (API, docs/market-data.md, frontend).
"""

import hashlib
import math
from datetime import UTC, datetime
from decimal import Decimal

from app.services.market_data.provider import ProviderBar, SymbolNotSupportedError

SOURCE = "mock"

# Anchor for the closed-form bar index. Arbitrary but fixed — changing it
# would change every generated price, so it is not configurable.
_ANCHOR = datetime(2024, 1, 1, tzinfo=UTC)

_INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}

# Illustrative starting prices for development fixtures only.
_BASE_PRICES: dict[str, Decimal] = {
    "AAPL": Decimal("190.00"),
    "MSFT": Decimal("410.00"),
    "NVDA": Decimal("125.00"),
    "AMZN": Decimal("180.00"),
    "TSLA": Decimal("240.00"),
}

_CENTS = Decimal("0.01")
_UNIT = Decimal("1")


def _bar_index(timestamp: datetime, interval: str) -> int:
    step = _INTERVAL_SECONDS[interval]
    delta_seconds = (timestamp - _ANCHOR).total_seconds()
    return math.floor(delta_seconds / step)


def _bar_timestamp(index: int, interval: str) -> datetime:
    step = _INTERVAL_SECONDS[interval]
    return datetime.fromtimestamp(_ANCHOR.timestamp() + index * step, tz=UTC)


def _deterministic_unit(symbol: str, interval: str, index: int, salt: str) -> float:
    """Deterministic pseudo-random value in [0, 1), derived from a hash —
    no shared RNG state, so any (symbol, interval, index) is independently
    reproducible regardless of call order."""
    key = f"{symbol}:{interval}:{index}:{salt}".encode()
    digest = hashlib.sha256(key).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _close_price(symbol: str, interval: str, index: int) -> Decimal:
    base = _BASE_PRICES[symbol]
    # A smooth deterministic "trend" (two superimposed sine waves) plus a
    # small deterministic "noise" term — reads as a realistic walk while
    # remaining a pure function of the index (closed form, no iteration).
    trend = math.sin(index * 0.05) * 0.03 + math.sin(index * 0.011) * 0.06
    noise = (_deterministic_unit(symbol, interval, index, "close") - 0.5) * 0.02
    multiplier = Decimal(str(round(1 + trend + noise, 6)))
    price = base * multiplier
    return price.quantize(_CENTS)


def _generate_bar(symbol: str, interval: str, index: int) -> ProviderBar:
    base = _BASE_PRICES[symbol]
    open_price = _close_price(symbol, interval, index - 1)
    close_price = _close_price(symbol, interval, index)

    spread_unit = Decimal(str(round(_deterministic_unit(symbol, interval, index, "range"), 6)))
    spread = (base * Decimal("0.004") * spread_unit).quantize(_CENTS)
    if spread <= 0:
        spread = _CENTS

    high_price = max(open_price, close_price) + spread
    low_price = min(open_price, close_price) - spread
    if low_price <= 0:
        low_price = _CENTS

    volume_unit = Decimal(str(round(_deterministic_unit(symbol, interval, index, "volume"), 6)))
    volume = (Decimal("500000") + volume_unit * Decimal("2000000")).quantize(_UNIT)

    return ProviderBar(
        symbol=symbol,
        timestamp=_bar_timestamp(index, interval),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        interval=interval,
        source=SOURCE,
    )


class MockMarketDataProvider:
    """Deterministic, in-process implementation of MarketDataProvider.
    See provider.py for the interface every provider (mock or real)
    implements."""

    def supported_symbols(self) -> list[str]:
        return sorted(_BASE_PRICES.keys())

    def get_quote(self, symbol: str, *, as_of: datetime) -> ProviderBar:
        if symbol not in _BASE_PRICES:
            raise SymbolNotSupportedError(symbol)
        index = _bar_index(as_of, "1m")
        return _generate_bar(symbol, "1m", index)

    def get_history(
        self, symbol: str, *, start: datetime, end: datetime, interval: str
    ) -> list[ProviderBar]:
        if symbol not in _BASE_PRICES:
            raise SymbolNotSupportedError(symbol)
        if interval not in _INTERVAL_SECONDS:
            raise ValueError(f"unsupported interval: {interval!r}")

        start_index = _bar_index(start, interval)
        end_index = _bar_index(end, interval)
        return [_generate_bar(symbol, interval, i) for i in range(start_index, end_index + 1)]
