"""GET /command-center (Phase 9) — a single read-only aggregation of
everything the MarketPilot Command Center needs on load: system health,
one symbol's market snapshot, a watchlist strip, recent signals, recent
AI analyses, the risk summary, the paper portfolio (with open positions
and recent fills), and a merged recent-activity feed.

This exists purely to cut the dashboard's per-load request count (Step
"API efficiency") — every value here already comes from an existing
service's existing public method; this router composes and merges,
it never recomputes or duplicates domain logic. Full detail:
docs/command-center.md.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_ai_analyst_service,
    get_market_data_service,
    get_paper_trading_service,
    get_risk_service,
    get_signal_service,
    get_technical_analysis_service,
)
from app.core.errors import ValidationAppError
from app.db import redis as redis_db
from app.db import session as db_session
from app.models.ai_analysis import AIAnalysis
from app.models.market_data import SUPPORTED_INTERVALS
from app.models.paper_trading import PaperFill, PaperPosition
from app.models.risk import RiskEvaluation
from app.models.signal import Signal
from app.schemas.ai import AIAnalysisResponse, AIStatusResponse
from app.schemas.analysis import MarketFeaturesResponse, PriceInfo, RegimeResponse
from app.schemas.command_center import (
    ActivityEventResponse,
    CommandCenterResponse,
    MarketSnapshotResponse,
    SystemHealthResponse,
    WatchlistQuoteResponse,
)
from app.schemas.paper import PaperFillResponse, PaperPortfolioResponse, PaperPositionResponse
from app.schemas.risk import PortfolioStateResponse, RiskPolicyResponse, RiskSummaryResponse
from app.schemas.signal import SignalResponse
from app.services.ai_analyst.service import AIAnalystService
from app.services.market_data import MarketDataService
from app.services.paper_trading.service import PaperTradingService
from app.services.risk_engine.service import RiskService
from app.services.signal_engine import SignalService
from app.services.technical_analysis import TechnicalAnalysisService

router = APIRouter(tags=["command-center"])

_DEFAULT_WATCHLIST = ("AAPL", "MSFT", "NVDA", "TSLA")
_ACTIVITY_PULL_MULTIPLIER = 3  # pull more rows per source than the final cap, pre-merge


def _strategy_label(strategy_id: str, strategy_version: str) -> str:
    return f"{strategy_id}_v{strategy_version.split('.')[0]}"


def _signal_response(row: Signal) -> SignalResponse:
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


def _ai_analysis_response(row: AIAnalysis) -> AIAnalysisResponse:
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


def _signal_activity(row: Signal) -> ActivityEventResponse:
    return ActivityEventResponse(
        type="SIGNAL_GENERATED",
        timestamp=row.generated_at,
        symbol=row.asset.symbol,
        summary=f"{row.signal} signal generated ({row.strategy_id})",
        signal_id=row.id,
    )


def _risk_activity(row: RiskEvaluation) -> ActivityEventResponse:
    event_type = "RISK_APPROVED" if row.decision == "APPROVED" else "RISK_REJECTED"
    return ActivityEventResponse(
        type=event_type,
        timestamp=row.evaluated_at,
        symbol=row.signal.asset.symbol,
        summary=(
            f"Risk {row.decision.lower()} for {row.signal.asset.symbol}"
            + (f" — {row.reasons[0]}" if row.decision == "REJECTED" and row.reasons else "")
        ),
        signal_id=row.signal_id,
    )


def _ai_activity(row: AIAnalysis) -> ActivityEventResponse:
    return ActivityEventResponse(
        type="AI_ANALYSIS_COMPLETED",
        timestamp=row.generated_at,
        symbol=row.asset.symbol,
        summary=f"AI analysis completed — suggested {row.suggested_action}",
        signal_id=row.signal_id,
    )


def _fill_activity(row: PaperFill) -> ActivityEventResponse:
    is_close = row.realized_pnl is not None
    return ActivityEventResponse(
        type="POSITION_CLOSED" if is_close else "PAPER_ORDER_FILLED",
        timestamp=row.timestamp,
        symbol=row.asset.symbol,
        summary=(
            f"Position closed — realized P/L {row.realized_pnl}"
            if is_close
            else f"Paper order filled — {row.side} {row.quantity} @ {row.fill_price}"
        ),
        signal_id=None,
    )


@router.get("/command-center", response_model=CommandCenterResponse)
async def get_command_center(
    symbol: str = Query("AAPL", description="The primary/selected symbol for Market Overview"),
    interval: str = Query("1d", description="One of: " + ", ".join(SUPPORTED_INTERVALS)),
    watchlist: str = Query(
        ",".join(_DEFAULT_WATCHLIST), description="Comma-separated symbols for the watchlist strip"
    ),
    activity_limit: int = Query(15, ge=1, le=50),
    technical_analysis_service: TechnicalAnalysisService = Depends(get_technical_analysis_service),
    market_data_service: MarketDataService = Depends(get_market_data_service),
    signal_service: SignalService = Depends(get_signal_service),
    risk_service: RiskService = Depends(get_risk_service),
    paper_trading_service: PaperTradingService = Depends(get_paper_trading_service),
    ai_service: AIAnalystService = Depends(get_ai_analyst_service),
) -> CommandCenterResponse:
    if interval not in SUPPORTED_INTERVALS:
        raise ValidationAppError(
            f"unsupported interval: {interval!r}",
            details={"interval": interval, "supported": list(SUPPORTED_INTERVALS)},
        )
    watchlist_symbols = [s.strip().upper() for s in watchlist.split(",") if s.strip()]

    # --- market snapshot for the selected symbol (propagates 404 if
    # `symbol` is unknown — the same behavior GET /analysis/{symbol} has,
    # since this is the one section the caller explicitly asked for by
    # name, unlike the best-effort watchlist strip below) ---
    snapshot = await technical_analysis_service.get_snapshot(symbol, interval=interval)
    market = MarketSnapshotResponse(
        symbol=snapshot.asset.symbol,
        asset_id=snapshot.asset.id,
        interval=snapshot.interval,
        source=snapshot.source,
        is_mock=snapshot.source == "mock",
        calculated_at=snapshot.calculated_at,
        candle_count=snapshot.candle_count,
        price=PriceInfo(timestamp=snapshot.latest_timestamp, close=snapshot.latest_close),
        features=MarketFeaturesResponse(
            price_above_ema21=snapshot.features.price_above_ema21,
            ema9_above_ema21=snapshot.features.ema9_above_ema21,
            ema21_above_ema50=snapshot.features.ema21_above_ema50,
            ema50_above_ema200=snapshot.features.ema50_above_ema200,
            trend_alignment_score=snapshot.features.trend_alignment_score,
            trend_alignment_label=snapshot.features.trend_alignment_label,
            trend_direction=snapshot.features.trend_direction,
            rsi_state=snapshot.features.rsi_state,
            macd_state=snapshot.features.macd_state,
            volume_state=snapshot.features.volume_state,
            volatility_state=snapshot.features.volatility_state,
        ),
        regime=RegimeResponse(regime=snapshot.regime.regime, reasons=snapshot.regime.reasons),
    )

    # --- watchlist: best-effort per symbol; one bad/unknown symbol never
    # fails the whole snapshot ---
    watchlist_rows: list[WatchlistQuoteResponse] = []
    any_quote_succeeded = False
    for wl_symbol in watchlist_symbols:
        try:
            asset, bar = await market_data_service.get_quote(wl_symbol)
        except Exception:  # noqa: BLE001 — a single bad watchlist symbol is not fatal
            continue
        any_quote_succeeded = True
        change_pct = ((bar.close - bar.open) / bar.open * 100) if bar.open else None
        watchlist_rows.append(
            WatchlistQuoteResponse(
                symbol=asset.symbol,
                close=bar.close,
                change_pct=change_pct,
                timestamp=bar.timestamp,
                source=bar.source,
                is_mock=bar.source == "mock",
            )
        )

    # --- signals, AI analyses, risk, portfolio (all plain reads) ---
    signal_rows = await signal_service.list_signals(limit=10)
    ai_rows = await ai_service.list_analyses(limit=10)
    policy = await risk_service.get_active_policy()
    portfolio_snapshot = await risk_service.get_portfolio_snapshot()
    portfolio_state = await paper_trading_service.get_portfolio_state()
    position_rows = await paper_trading_service.list_positions(status="OPEN")
    fill_rows = await paper_trading_service.list_fills(limit=10)

    hundred = Decimal("100")
    drawdown_pct = (
        (portfolio_snapshot.high_water_mark - portfolio_snapshot.equity)
        / portfolio_snapshot.high_water_mark
        * hundred
        if portfolio_snapshot.high_water_mark > 0
        else Decimal("0")
    )
    max_exposure_value = portfolio_snapshot.equity * policy.max_portfolio_exposure_pct / hundred
    available_exposure_value = max_exposure_value - portfolio_snapshot.open_position_value
    risk = RiskSummaryResponse(
        portfolio=PortfolioStateResponse(
            equity=portfolio_snapshot.equity,
            cash=portfolio_snapshot.cash,
            high_water_mark=portfolio_snapshot.high_water_mark,
            drawdown_pct=drawdown_pct,
            open_position_count=portfolio_snapshot.open_position_count,
            open_position_value=portfolio_snapshot.open_position_value,
            available_exposure_value=(
                available_exposure_value if available_exposure_value > 0 else Decimal("0")
            ),
            realized_pl_today=portfolio_snapshot.realized_pl_today,
            as_of=portfolio_snapshot.as_of,
        ),
        policy=RiskPolicyResponse(
            id=policy.id,
            name=policy.name,
            version=policy.version,
            enabled=policy.enabled,
            is_active=policy.is_active,
            max_position_size_pct=policy.max_position_size_pct,
            max_portfolio_exposure_pct=policy.max_portfolio_exposure_pct,
            max_daily_loss_pct=policy.max_daily_loss_pct,
            max_drawdown_pct=policy.max_drawdown_pct,
            stop_loss_pct=policy.stop_loss_pct,
            take_profit_pct=policy.take_profit_pct,
            risk_per_trade_pct=policy.risk_per_trade_pct,
            max_concurrent_positions=policy.max_concurrent_positions,
            cooldown_after_loss_minutes=policy.cooldown_after_loss_minutes,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
        ),
    )
    portfolio = PaperPortfolioResponse(
        starting_equity=portfolio_state.starting_equity,
        cash=portfolio_state.cash,
        market_value=portfolio_state.market_value,
        equity=portfolio_state.equity,
        realized_pnl_total=portfolio_state.realized_pnl_total,
        unrealized_pnl=portfolio_state.unrealized_pnl,
        total_pnl=portfolio_state.total_pnl,
        daily_pnl=portfolio_state.daily_pnl,
        peak_equity=portfolio_state.peak_equity,
        drawdown_pct=portfolio_state.drawdown_pct,
        open_position_count=portfolio_state.open_position_count,
        as_of=portfolio_state.as_of,
    )
    positions = [await _position_response(row, paper_trading_service) for row in position_rows]

    # --- system health ---
    database_ok = await db_session.check_connection()
    redis_ok = await redis_db.check_connection()
    ai_status = ai_service.get_status()
    system_health = SystemHealthResponse(
        api="ok",
        database="ok" if database_ok else "down",
        redis="ok" if redis_ok else "down",
        market_data="ok" if any_quote_succeeded else "down",
        ai=AIStatusResponse.model_validate(ai_status),
    )

    # --- recent activity: merge + sort existing reads, cap at activity_limit ---
    risk_eval_rows = await risk_service.list_evaluations(
        limit=activity_limit * _ACTIVITY_PULL_MULTIPLIER
    )
    activity_fill_rows = await paper_trading_service.list_fills(
        limit=activity_limit * _ACTIVITY_PULL_MULTIPLIER
    )
    activity_signal_rows = await signal_service.list_signals(
        limit=activity_limit * _ACTIVITY_PULL_MULTIPLIER
    )
    activity_ai_rows = await ai_service.list_analyses(
        limit=activity_limit * _ACTIVITY_PULL_MULTIPLIER
    )

    events: list[ActivityEventResponse] = (
        [_signal_activity(row) for row in activity_signal_rows]
        + [_risk_activity(row) for row in risk_eval_rows]
        + [_ai_activity(row) for row in activity_ai_rows]
        + [_fill_activity(row) for row in activity_fill_rows]
    )

    def _sort_key(event: ActivityEventResponse) -> datetime:
        ts = event.timestamp
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)

    events.sort(key=_sort_key, reverse=True)
    recent_activity = events[:activity_limit]

    return CommandCenterResponse(
        generated_at=datetime.now(UTC),
        system_health=system_health,
        market=market,
        watchlist=watchlist_rows,
        signals=[_signal_response(row) for row in signal_rows],
        ai_analyses=[_ai_analysis_response(row) for row in ai_rows],
        risk=risk,
        portfolio=portfolio,
        positions=positions,
        recent_fills=[_fill_response(row) for row in fill_rows],
        recent_activity=recent_activity,
    )
