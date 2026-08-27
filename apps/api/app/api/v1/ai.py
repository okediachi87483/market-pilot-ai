"""AI Analyst endpoints (Step 18). All under `/api/v1/ai` — full detail
in docs/api.md and docs/ai-analyst.md.

`GET /ai/status` reports whether the provider is configured/available
by name only — it never returns the API key, and `available` is a
proxy for `configured` (no live Claude call is made just to answer a
status check, Step 25's cost-control policy).

`POST /ai/analyze/{signal_id}` never places, modifies, or executes
anything — it is a read of what the AI Analyst currently observes,
exactly like `POST /signals/evaluate/{symbol}` and
`POST /risk/evaluate/{signal_id}` before it.
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_ai_analyst_service
from app.models.ai_analysis import AIAnalysis
from app.schemas.ai import AIAnalysisResponse, AIStatusResponse
from app.services.ai_analyst.service import AIAnalystService

router = APIRouter(prefix="/ai", tags=["ai"])


def _analysis_response(row: AIAnalysis) -> AIAnalysisResponse:
    return AIAnalysisResponse(
        id=row.id,
        signal_id=row.signal_id,
        symbol=row.asset.symbol,
        interval=row.interval,
        provider=row.provider,
        model=row.model,
        prompt_version=row.prompt_version,
        market_summary=row.market_summary,
        thesis=row.thesis,
        supporting_evidence=row.supporting_evidence,
        contradicting_evidence=row.contradicting_evidence,
        risks=row.risks,
        invalidating_conditions=row.invalidating_conditions,
        suggested_action=row.suggested_action,
        action_rationale=row.action_rationale,
        uncertainty=row.uncertainty,
        model_metadata=row.model_metadata,
        generated_at=row.generated_at,
        created_at=row.created_at,
    )


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status(
    service: AIAnalystService = Depends(get_ai_analyst_service),
) -> AIStatusResponse:
    return AIStatusResponse.model_validate(service.get_status())


@router.post("/analyze/{signal_id}", response_model=AIAnalysisResponse)
async def analyze_signal(
    signal_id: uuid.UUID, service: AIAnalystService = Depends(get_ai_analyst_service)
) -> AIAnalysisResponse:
    """Analyzes `signal_id`'s current evidence (technical data, the
    signal itself, and the risk decision if one exists) and returns the
    resulting analysis — existing (deduplicated within the cooldown
    window) or newly generated. `404` unknown signal; `503` if the
    provider is not configured or the Claude call fails; `422` if the
    response fails schema or content-safety validation."""
    row = await service.analyze_signal(signal_id)
    return _analysis_response(row)


@router.get("/analyses", response_model=list[AIAnalysisResponse])
async def list_ai_analyses(
    symbol: str | None = Query(None, description="Filter by asset symbol, e.g. 'AAPL'"),
    signal_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    service: AIAnalystService = Depends(get_ai_analyst_service),
) -> list[AIAnalysisResponse]:
    rows = await service.list_analyses(symbol=symbol, signal_id=signal_id, limit=limit)
    return [_analysis_response(row) for row in rows]


@router.get("/analyses/{analysis_id}", response_model=AIAnalysisResponse)
async def get_ai_analysis(
    analysis_id: uuid.UUID, service: AIAnalystService = Depends(get_ai_analyst_service)
) -> AIAnalysisResponse:
    row = await service.get_analysis(analysis_id)
    return _analysis_response(row)


@router.get("/signals/{signal_id}", response_model=list[AIAnalysisResponse])
async def list_ai_analyses_for_signal(
    signal_id: uuid.UUID, service: AIAnalystService = Depends(get_ai_analyst_service)
) -> list[AIAnalysisResponse]:
    """Equivalent to `GET /ai/analyses?signal_id=...` — provided as its
    own path because Step 18 lists it explicitly alongside the
    query-filtered list endpoint."""
    rows = await service.list_for_signal(signal_id)
    return [_analysis_response(row) for row in rows]
