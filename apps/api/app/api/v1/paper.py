"""Paper trading endpoints (Step 22). All under `/api/v1/paper` — full
detail in docs/api.md and docs/paper-trading.md.

`POST /paper/execute/{signal_id}` accepts only a `RISK_APPROVED` signal
— `404` unknown signal, `409` if it's `CANDIDATE`, `RISK_REJECTED`, or
already has a paper order (idempotency, Step 19). Never places a real
order anywhere; this is a simulated fill against the same market data
the rest of the platform reads.
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_paper_trading_service
from app.models.paper_trading import PaperFill, PaperOrder, PaperPosition
from app.schemas.paper import (
    PaperFillResponse,
    PaperOrderResponse,
    PaperPortfolioResponse,
    PaperPositionResponse,
)
from app.services.paper_trading.portfolio import PortfolioState
from app.services.paper_trading.service import PaperTradingService

router = APIRouter(prefix="/paper", tags=["paper"])


def _order_response(row: PaperOrder) -> PaperOrderResponse:
    return PaperOrderResponse(
        id=row.id,
        signal_id=row.signal_id,
        symbol=row.asset.symbol,
        side=row.side,
        order_type=row.order_type,
        quantity=row.quantity,
        requested_price=row.requested_price,
        status=row.status,
        filled_quantity=row.filled_quantity,
        average_fill_price=row.average_fill_price,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        submitted_at=row.submitted_at,
        filled_at=row.filled_at,
        cancelled_at=row.cancelled_at,
    )


def _fill_response(row: PaperFill) -> PaperFillResponse:
    return PaperFillResponse(
        id=row.id,
        order_id=row.order_id,
        symbol=row.asset.symbol,
        side=row.side,
        quantity=row.quantity,
        fill_price=row.fill_price,
        fee=row.fee,
        realized_pnl=row.realized_pnl,
        timestamp=row.timestamp,
    )


async def _position_response(
    row: PaperPosition, service: PaperTradingService
) -> PaperPositionResponse:
    market_data = await service.get_position_market_data(row)
    return PaperPositionResponse(
        id=row.id,
        symbol=row.asset.symbol,
        quantity=row.quantity,
        avg_entry_price=row.avg_entry_price,
        current_price=market_data.current_price,
        market_value=market_data.market_value,
        unrealized_pnl=market_data.unrealized_pnl,
        realized_pnl=row.realized_pnl,
        status=row.status,
        opened_at=row.opened_at,
        updated_at=row.updated_at,
        closed_at=row.closed_at,
    )


def _portfolio_response(state: PortfolioState) -> PaperPortfolioResponse:
    return PaperPortfolioResponse(
        starting_equity=state.starting_equity,
        cash=state.cash,
        market_value=state.market_value,
        equity=state.equity,
        realized_pnl_total=state.realized_pnl_total,
        unrealized_pnl=state.unrealized_pnl,
        total_pnl=state.total_pnl,
        daily_pnl=state.daily_pnl,
        peak_equity=state.peak_equity,
        drawdown_pct=state.drawdown_pct,
        open_position_count=state.open_position_count,
        as_of=state.as_of,
    )


@router.get("/portfolio", response_model=PaperPortfolioResponse)
async def get_paper_portfolio(
    service: PaperTradingService = Depends(get_paper_trading_service),
) -> PaperPortfolioResponse:
    state = await service.get_portfolio_state()
    return _portfolio_response(state)


@router.get("/positions", response_model=list[PaperPositionResponse])
async def list_paper_positions(
    status: str | None = Query(None, description="One of: OPEN, CLOSED"),
    service: PaperTradingService = Depends(get_paper_trading_service),
) -> list[PaperPositionResponse]:
    rows = await service.list_positions(status=status)
    return [await _position_response(row, service) for row in rows]


@router.get("/orders", response_model=list[PaperOrderResponse])
async def list_paper_orders(
    symbol: str | None = Query(None),
    status: str | None = Query(None, description="One of: PENDING, FILLED, REJECTED, CANCELLED"),
    limit: int = Query(50, ge=1, le=200),
    service: PaperTradingService = Depends(get_paper_trading_service),
) -> list[PaperOrderResponse]:
    rows = await service.list_orders(symbol=symbol, status=status, limit=limit)
    return [_order_response(row) for row in rows]


@router.get("/orders/{order_id}", response_model=PaperOrderResponse)
async def get_paper_order(
    order_id: uuid.UUID, service: PaperTradingService = Depends(get_paper_trading_service)
) -> PaperOrderResponse:
    row = await service.get_order(order_id)
    return _order_response(row)


@router.get("/fills", response_model=list[PaperFillResponse])
async def list_paper_fills(
    symbol: str | None = Query(None),
    order_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    service: PaperTradingService = Depends(get_paper_trading_service),
) -> list[PaperFillResponse]:
    rows = await service.list_fills(symbol=symbol, order_id=order_id, limit=limit)
    return [_fill_response(row) for row in rows]


@router.post("/execute/{signal_id}", response_model=PaperOrderResponse)
async def execute_paper_order(
    signal_id: uuid.UUID, service: PaperTradingService = Depends(get_paper_trading_service)
) -> PaperOrderResponse:
    order = await service.execute_signal(signal_id)
    return _order_response(order)


@router.post("/positions/{symbol}/close", response_model=PaperOrderResponse)
async def close_paper_position(
    symbol: str, service: PaperTradingService = Depends(get_paper_trading_service)
) -> PaperOrderResponse:
    order = await service.close_position(symbol)
    return _order_response(order)
