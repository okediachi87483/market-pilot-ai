import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class OHLCVBar(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class QuoteResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    source: str
    is_mock: bool
    bar: OHLCVBar


class HistoryResponse(BaseModel):
    symbol: str
    asset_id: uuid.UUID
    interval: str
    source: str
    is_mock: bool
    start: datetime
    end: datetime
    count: int
    bars: list[OHLCVBar]
