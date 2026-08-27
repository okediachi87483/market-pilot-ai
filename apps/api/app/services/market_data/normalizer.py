"""OHLCV normalization — the NORMALIZER stage of the ingestion pipeline.

Runs only on bars that already passed validation. Normalization changes
*representation*, never *meaning*: casing, timezone, decimal precision,
and identifier casing are canonicalized; nothing about what the data says
is altered. See docs/market-data.md §"Timestamp conventions" for the UTC
policy this enforces.
"""

import dataclasses
from datetime import UTC
from decimal import Decimal

from app.services.market_data.provider import ProviderBar

# Matches the column precision declared in app/models/market_data.py
# (PRICE = Numeric(20, 8), QUANTITY = Numeric(28, 10)) — normalization
# quantizes to exactly what persistence expects, so no implicit rounding
# happens at the database layer.
_PRICE_EXPONENT = "0.00000001"
_QUANTITY_EXPONENT = "0.0000000001"


def normalize_bar(bar: ProviderBar) -> ProviderBar:
    timestamp = bar.timestamp
    if timestamp.tzinfo != UTC:
        timestamp = timestamp.astimezone(UTC)

    return dataclasses.replace(
        bar,
        symbol=bar.symbol.strip().upper(),
        timestamp=timestamp,
        open=bar.open.quantize(Decimal(_PRICE_EXPONENT)),
        high=bar.high.quantize(Decimal(_PRICE_EXPONENT)),
        low=bar.low.quantize(Decimal(_PRICE_EXPONENT)),
        close=bar.close.quantize(Decimal(_PRICE_EXPONENT)),
        volume=bar.volume.quantize(Decimal(_QUANTITY_EXPONENT)),
        interval=bar.interval.strip().lower(),
        source=bar.source.strip().lower(),
    )
