import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PaperOrderResponse(BaseModel):
    id: uuid.UUID
    signal_id: uuid.UUID | None
    symbol: str
    side: str  # "BUY" | "SELL"
    order_type: str
    quantity: Decimal
    requested_price: Decimal
    status: str  # "PENDING" | "FILLED" | "REJECTED" | "CANCELLED"
    filled_quantity: Decimal
    average_fill_price: Decimal | None
    rejection_reason: str | None
    created_at: datetime
    submitted_at: datetime | None
    filled_at: datetime | None
    cancelled_at: datetime | None


class PaperFillResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    symbol: str
    side: str
    quantity: Decimal
    fill_price: Decimal
    fee: Decimal
    realized_pnl: Decimal | None
    timestamp: datetime


class PaperPositionResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    status: str  # "OPEN" | "CLOSED"
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class PaperPortfolioResponse(BaseModel):
    starting_equity: Decimal
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl_total: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    daily_pnl: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    open_position_count: int
    as_of: datetime
