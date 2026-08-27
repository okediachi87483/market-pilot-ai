"""Risk endpoints (Step 19/20). All under `/api/v1/risk` — full detail in
docs/api.md and docs/risk-engine.md.

Adds one endpoint beyond the phase's literal list —
`GET /risk/evaluations/{evaluation_id}` — for the same reason Phase 3/5
each added a couple of endpoints beyond their own sketch: a natural
single-item GET alongside an existing list endpoint, consistent with
`GET /signals/{id}` next to `GET /signals` (Step 19: "preserve
consistency rather than creating duplicates").
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_risk_service
from app.models.risk import RISK_DECISIONS, RiskEvaluation, RiskPolicy
from app.schemas.risk import (
    PortfolioStateResponse,
    RiskCheckResponse,
    RiskEvaluationResponse,
    RiskPolicyResponse,
    RiskPolicyUpdateRequest,
    RiskSummaryResponse,
)
from app.services.risk_engine.service import RiskService
from app.services.risk_engine.types import PortfolioSnapshot

router = APIRouter(prefix="/risk", tags=["risk"])

HUNDRED = Decimal("100")


def _policy_response(row: RiskPolicy) -> RiskPolicyResponse:
    return RiskPolicyResponse(
        id=row.id,
        name=row.name,
        version=row.version,
        enabled=row.enabled,
        is_active=row.is_active,
        max_position_size_pct=row.max_position_size_pct,
        max_portfolio_exposure_pct=row.max_portfolio_exposure_pct,
        max_daily_loss_pct=row.max_daily_loss_pct,
        max_drawdown_pct=row.max_drawdown_pct,
        stop_loss_pct=row.stop_loss_pct,
        take_profit_pct=row.take_profit_pct,
        risk_per_trade_pct=row.risk_per_trade_pct,
        max_concurrent_positions=row.max_concurrent_positions,
        cooldown_after_loss_minutes=row.cooldown_after_loss_minutes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _portfolio_response(snapshot: PortfolioSnapshot, policy: RiskPolicy) -> PortfolioStateResponse:
    drawdown_pct = (
        (snapshot.high_water_mark - snapshot.equity) / snapshot.high_water_mark * HUNDRED
        if snapshot.high_water_mark > 0
        else Decimal("0")
    )
    max_exposure_value = snapshot.equity * policy.max_portfolio_exposure_pct / HUNDRED
    available_exposure_value = max_exposure_value - snapshot.open_position_value
    return PortfolioStateResponse(
        equity=snapshot.equity,
        cash=snapshot.cash,
        high_water_mark=snapshot.high_water_mark,
        drawdown_pct=drawdown_pct,
        open_position_count=snapshot.open_position_count,
        open_position_value=snapshot.open_position_value,
        available_exposure_value=(
            available_exposure_value if available_exposure_value > 0 else Decimal("0")
        ),
        realized_pl_today=snapshot.realized_pl_today,
        as_of=snapshot.as_of,
    )


def _evaluation_response(row: RiskEvaluation) -> RiskEvaluationResponse:
    return RiskEvaluationResponse(
        id=row.id,
        signal_id=row.signal_id,
        symbol=row.signal.asset.symbol,
        policy_id=row.policy_id,
        policy_version=row.policy_version,
        decision=row.decision,
        reasons=row.reasons,
        checks=[RiskCheckResponse.model_validate(c) for c in row.checks],
        calculated_position_size=row.calculated_position_size,
        entry_price=row.entry_price,
        stop_loss_price=row.stop_loss_price,
        take_profit_price=row.take_profit_price,
        position_value=row.position_value,
        portfolio_snapshot=row.portfolio_snapshot,
        evaluated_at=row.evaluated_at,
        created_at=row.created_at,
    )


@router.get("", response_model=RiskSummaryResponse)
async def get_risk_summary(service: RiskService = Depends(get_risk_service)) -> RiskSummaryResponse:
    policy = await service.get_active_policy()
    snapshot = await service.get_portfolio_snapshot()
    return RiskSummaryResponse(
        portfolio=_portfolio_response(snapshot, policy), policy=_policy_response(policy)
    )


@router.get("/rules", response_model=RiskPolicyResponse)
async def get_risk_rules(service: RiskService = Depends(get_risk_service)) -> RiskPolicyResponse:
    policy = await service.get_active_policy()
    return _policy_response(policy)


@router.put("/rules", response_model=RiskPolicyResponse)
async def update_risk_rules(
    body: RiskPolicyUpdateRequest, service: RiskService = Depends(get_risk_service)
) -> RiskPolicyResponse:
    policy = await service.update_policy(body.model_dump())
    return _policy_response(policy)


@router.post("/evaluate/{signal_id}", response_model=RiskEvaluationResponse)
async def evaluate_risk(
    signal_id: uuid.UUID, service: RiskService = Depends(get_risk_service)
) -> RiskEvaluationResponse:
    """Risk-evaluates a `CANDIDATE` signal right now: computes position
    size/stop-loss/take-profit, runs the full check pipeline, transitions
    the signal to `RISK_APPROVED`/`RISK_REJECTED`, and persists the audit
    row. `404` if the signal doesn't exist; `409` if it isn't currently
    `CANDIDATE` (docs/risk-engine.md). Never places, fills, or simulates
    a trade — that is Phase 7."""
    evaluation = await service.evaluate_signal(signal_id)
    return _evaluation_response(evaluation)


@router.get("/evaluations", response_model=list[RiskEvaluationResponse])
async def list_risk_evaluations(
    signal_id: uuid.UUID | None = Query(None),
    decision: str | None = Query(None, description="One of: " + ", ".join(RISK_DECISIONS)),
    symbol: str | None = Query(None, description="Filter by asset symbol, e.g. 'AAPL'"),
    limit: int = Query(50, ge=1, le=200),
    service: RiskService = Depends(get_risk_service),
) -> list[RiskEvaluationResponse]:
    rows = await service.list_evaluations(
        signal_id=signal_id, decision=decision, symbol=symbol, limit=limit
    )
    return [_evaluation_response(row) for row in rows]


@router.get("/evaluations/{evaluation_id}", response_model=RiskEvaluationResponse)
async def get_risk_evaluation(
    evaluation_id: uuid.UUID, service: RiskService = Depends(get_risk_service)
) -> RiskEvaluationResponse:
    evaluation = await service.get_evaluation(evaluation_id)
    return _evaluation_response(evaluation)
