import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# Field bounds mirror the CHECK constraints on `risk_policies`
# (app/models/risk.py) exactly (Step 20: "use reasonable absolute
# bounds in addition to business rules") — an out-of-bounds value is
# rejected with a clean 422 here, never reaching the database.


class RiskPolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    enabled: bool
    is_active: bool
    max_position_size_pct: Decimal
    max_portfolio_exposure_pct: Decimal
    max_daily_loss_pct: Decimal
    max_drawdown_pct: Decimal
    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    risk_per_trade_pct: Decimal
    max_concurrent_positions: int
    cooldown_after_loss_minutes: int
    created_at: datetime
    updated_at: datetime


class RiskPolicyUpdateRequest(BaseModel):
    enabled: bool
    max_position_size_pct: Decimal = Field(gt=0, le=100)
    max_portfolio_exposure_pct: Decimal = Field(gt=0, le=100)
    max_daily_loss_pct: Decimal = Field(gt=0, le=100)
    max_drawdown_pct: Decimal = Field(gt=0, le=100)
    stop_loss_pct: Decimal = Field(gt=0, lt=100)
    take_profit_pct: Decimal = Field(gt=0, le=1000)
    risk_per_trade_pct: Decimal = Field(gt=0, le=100)
    max_concurrent_positions: int = Field(ge=1, le=1000)
    cooldown_after_loss_minutes: int = Field(ge=0, le=10080)


class RiskCheckResponse(BaseModel):
    name: str
    passed: bool
    detail: str
    skipped: bool


class RiskEvaluationResponse(BaseModel):
    id: uuid.UUID
    signal_id: uuid.UUID
    symbol: str
    policy_id: uuid.UUID
    policy_version: int
    decision: str  # "APPROVED" | "REJECTED"
    reasons: list[str]
    checks: list[RiskCheckResponse]
    calculated_position_size: Decimal | None
    entry_price: Decimal | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    position_value: Decimal | None
    portfolio_snapshot: dict[str, object]
    evaluated_at: datetime
    created_at: datetime


class PortfolioStateResponse(BaseModel):
    equity: Decimal
    cash: Decimal
    high_water_mark: Decimal
    drawdown_pct: Decimal
    open_position_count: int
    open_position_value: Decimal
    available_exposure_value: Decimal
    realized_pl_today: Decimal
    as_of: datetime


class RiskSummaryResponse(BaseModel):
    """`GET /risk` — the read model behind the Risk Center's "Portfolio
    Risk" panel (Step 21): current portfolio state alongside the active
    policy's limits, so the UI never has to compute a limit client-side."""

    portfolio: PortfolioStateResponse
    policy: RiskPolicyResponse
