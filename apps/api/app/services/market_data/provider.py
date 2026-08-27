"""Market data provider abstraction.

The rest of the application depends on this Protocol, never on a concrete
provider. Today the only implementation is MockMarketDataProvider
(mock_provider.py); a future real provider (Polygon, Alpaca, etc. — not
integrated yet, see docs/market-data.md) implements the same three
methods and can be swapped in via dependency injection without touching
the validator, normalizer, service, or API layer. See docs/architecture.md
§3 and ADR-context in docs/market-data.md.

This is intentionally minimal (Step 2: "do not over-engineer this") —
just enough surface for a current quote and historical OHLCV.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class SymbolNotSupportedError(ValueError):
    """Raised by a provider when asked for a symbol it doesn't serve."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"symbol not supported by provider: {symbol!r}")
        self.symbol = symbol


@dataclass(frozen=True)
class ProviderBar:
    """Raw output from a provider — the "RAW MARKET DATA" stage of the
    ingestion pipeline (docs/market-data.md), before validation or
    normalization. Deliberately the same shape a real provider's response
    would be mapped into by its own adapter."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    interval: str
    source: str


class MarketDataProvider(Protocol):
    def supported_symbols(self) -> list[str]:
        """Symbols this provider can serve. Used to validate a requested
        symbol before attempting ingestion."""
        ...

    def get_quote(self, symbol: str, *, as_of: datetime) -> ProviderBar:
        """The most recent bar at or before `as_of`."""
        ...

    def get_history(
        self, symbol: str, *, start: datetime, end: datetime, interval: str
    ) -> list[ProviderBar]:
        """Bars for `symbol` at `interval`, covering [start, end]."""
        ...
