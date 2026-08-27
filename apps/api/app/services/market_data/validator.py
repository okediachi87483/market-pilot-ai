"""OHLCV validation — the VALIDATOR stage of the ingestion pipeline.

Pure, side-effect-free: given a raw bar, return the list of rule
violations (empty means valid). Invalid data is rejected, never silently
corrected — see docs/market-data.md §"Validation". These same invariants
are additionally enforced as CHECK constraints at the database layer
(app/models/market_data.py) as a defense-in-depth backstop, not a
substitute for validating before persistence.
"""

import re
from datetime import datetime

from app.models.market_data import SUPPORTED_INTERVALS
from app.services.market_data.provider import ProviderBar

_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.\-/]{1,20}$")


def validate_bar(bar: ProviderBar) -> list[str]:
    errors: list[str] = []

    if not isinstance(bar.timestamp, datetime):
        errors.append("timestamp must be a datetime")
    elif bar.timestamp.tzinfo is None:
        errors.append("timestamp must be timezone-aware")

    if not bar.symbol or not _SYMBOL_PATTERN.match(bar.symbol):
        errors.append(f"symbol is not well-formed: {bar.symbol!r}")

    if bar.interval not in SUPPORTED_INTERVALS:
        errors.append(f"interval is not supported: {bar.interval!r}")

    for field_name in ("open", "high", "low", "close"):
        value = getattr(bar, field_name)
        if value is None or value <= 0:
            errors.append(f"{field_name} must be > 0, got {value!r}")

    if bar.volume is None or bar.volume < 0:
        errors.append(f"volume must be >= 0, got {bar.volume!r}")

    # Only check cross-field OHLC relationships once every individual
    # price is confirmed present and positive — comparing against a
    # missing/invalid value would produce a misleading second error.
    if not any(e.startswith(("open", "high", "low", "close")) for e in errors):
        if bar.high < bar.open:
            errors.append(f"high ({bar.high}) must be >= open ({bar.open})")
        if bar.high < bar.close:
            errors.append(f"high ({bar.high}) must be >= close ({bar.close})")
        if bar.high < bar.low:
            errors.append(f"high ({bar.high}) must be >= low ({bar.low})")
        if bar.low > bar.open:
            errors.append(f"low ({bar.low}) must be <= open ({bar.open})")
        if bar.low > bar.close:
            errors.append(f"low ({bar.low}) must be <= close ({bar.close})")

    return errors


def is_valid(bar: ProviderBar) -> bool:
    return not validate_bar(bar)
