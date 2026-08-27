from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_market_data_service
from app.core.errors import ValidationAppError
from app.models.market_data import SUPPORTED_INTERVALS
from app.schemas.market_data import HistoryResponse, OHLCVBar, QuoteResponse
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])

# Default lookback window when the caller doesn't specify `start` —
# chosen per interval so the default response is a reasonable size
# rather than either near-empty or hitting MAX_HISTORY_BARS.
_DEFAULT_HISTORY_WINDOW: dict[str, timedelta] = {
    "1m": timedelta(hours=2),
    "5m": timedelta(hours=8),
    "15m": timedelta(days=1),
    "1h": timedelta(days=7),
    "1d": timedelta(days=180),
}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/{symbol}", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    service: MarketDataService = Depends(get_market_data_service),
) -> QuoteResponse:
    asset, bar = await service.get_quote(symbol)
    return QuoteResponse(
        symbol=asset.symbol,
        asset_id=asset.id,
        interval=bar.interval,
        source=bar.source,
        is_mock=bar.source == "mock",
        bar=OHLCVBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        ),
    )


@router.get("/{symbol}/history", response_model=HistoryResponse)
async def get_history(
    symbol: str,
    interval: str = Query("1d", description="One of: " + ", ".join(SUPPORTED_INTERVALS)),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    service: MarketDataService = Depends(get_market_data_service),
) -> HistoryResponse:
    if interval not in SUPPORTED_INTERVALS:
        raise ValidationAppError(
            f"unsupported interval: {interval!r}",
            details={"interval": interval, "supported": list(SUPPORTED_INTERVALS)},
        )

    resolved_end = _as_utc(end) if end else datetime.now(UTC)
    resolved_start = _as_utc(start) if start else resolved_end - _DEFAULT_HISTORY_WINDOW[interval]

    if resolved_start > resolved_end:
        raise ValidationAppError(
            "start must be <= end",
            details={"start": resolved_start.isoformat(), "end": resolved_end.isoformat()},
        )

    asset, rows = await service.get_history(
        symbol, interval=interval, start=resolved_start, end=resolved_end
    )

    bars = [
        OHLCVBar(
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]
    source = rows[0].source if rows else "mock"

    return HistoryResponse(
        symbol=asset.symbol,
        asset_id=asset.id,
        interval=interval,
        source=source,
        is_mock=source == "mock",
        start=resolved_start,
        end=resolved_end,
        count=len(bars),
        bars=bars,
    )
