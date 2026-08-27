import uuid
from datetime import datetime

from pydantic import BaseModel


class SignalResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    interval: str
    signal: str  # "BUY" | "SELL" | "HOLD"
    strategy_id: str
    strategy_version: str
    strategy_label: str
    strength: str | None  # "WEAK" | "MODERATE" | "STRONG" | None
    market_regime: str
    reasons: list[str]
    supporting_features: dict[str, object]
    invalidating_conditions: list[str]
    status: str
    generated_at: datetime
    created_at: datetime


class EvaluateSignalResponse(SignalResponse):
    was_newly_created: bool
