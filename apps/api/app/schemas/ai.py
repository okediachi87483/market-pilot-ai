import uuid
from datetime import datetime

from pydantic import BaseModel


class AIAnalysisResponse(BaseModel):
    id: uuid.UUID
    signal_id: uuid.UUID
    symbol: str
    interval: str
    provider: str
    model: str
    prompt_version: str
    market_summary: str
    thesis: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    risks: list[str]
    invalidating_conditions: list[str]
    suggested_action: str  # "BUY" | "SELL" | "HOLD" | "NO_ACTION"
    action_rationale: str
    uncertainty: str  # "LOW" | "MEDIUM" | "HIGH"
    model_metadata: dict[str, object]
    generated_at: datetime
    created_at: datetime


class AIStatusResponse(BaseModel):
    configured: bool
    available: bool
    provider: str
    model: str
