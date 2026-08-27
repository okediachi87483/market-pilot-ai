"""Signal endpoints (Step 12).

Note on routing: the Phase 5 plan sketches both `GET /signals/{id}` and
`GET /signals/{symbol}` at the same path shape, which FastAPI cannot
distinguish (a UUID and a ticker are both just strings at the routing
layer). Resolved by folding symbol-scoped listing into `GET /signals`'s
`symbol` query parameter instead of a second path route — more
conventional REST besides (filtering belongs in the query string, not a
second path template for the same resource), and consistent with the
same kind of routing-ambiguity fix made in Phase 3 (docs/market-data.md).
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_signal_service
from app.models.signal import SIGNAL_STATUSES, Signal
from app.schemas.signal import EvaluateSignalResponse, SignalResponse
from app.services.signal_engine import SignalService

router = APIRouter(prefix="/signals", tags=["signals"])


def _strategy_label(strategy_id: str, strategy_version: str) -> str:
    return f"{strategy_id}_v{strategy_version.split('.')[0]}"


def _to_response(row: Signal) -> SignalResponse:
    return SignalResponse(
        id=row.id,
        symbol=row.asset.symbol,
        interval=row.interval,
        signal=row.signal,
        strategy_id=row.strategy_id,
        strategy_version=row.strategy_version,
        strategy_label=_strategy_label(row.strategy_id, row.strategy_version),
        strength=row.strength,
        market_regime=row.market_regime,
        reasons=row.reasons,
        supporting_features=row.supporting_features,
        invalidating_conditions=row.invalidating_conditions,
        status=row.status,
        generated_at=row.generated_at,
        created_at=row.created_at,
    )


@router.get("", response_model=list[SignalResponse])
async def list_signals(
    symbol: str | None = Query(None, description="Filter by asset symbol, e.g. 'AAPL'"),
    strategy_id: str | None = Query(None),
    status: str | None = Query(None, description="One of: " + ", ".join(SIGNAL_STATUSES)),
    interval: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    service: SignalService = Depends(get_signal_service),
) -> list[SignalResponse]:
    rows = await service.list_signals(
        symbol=symbol, strategy_id=strategy_id, status=status, interval=interval, limit=limit
    )
    return [_to_response(row) for row in rows]


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: uuid.UUID,
    service: SignalService = Depends(get_signal_service),
) -> SignalResponse:
    row = await service.get_signal(signal_id)
    return _to_response(row)


@router.post("/evaluate/{symbol}", response_model=EvaluateSignalResponse)
async def evaluate_signal(
    symbol: str,
    interval: str = Query("1h", description="One of: 1m, 5m, 15m, 1h, 1d"),
    service: SignalService = Depends(get_signal_service),
) -> EvaluateSignalResponse:
    """Evaluates `symbol` against the current `trend_momentum` strategy
    and returns a CANDIDATE signal. Never executes anything — this is a
    read of what the deterministic strategy currently suggests, not an
    order (docs/signal-engine.md)."""
    row, was_newly_created = await service.evaluate(symbol, interval=interval)
    response = _to_response(row)
    return EvaluateSignalResponse(**response.model_dump(), was_newly_created=was_newly_created)
