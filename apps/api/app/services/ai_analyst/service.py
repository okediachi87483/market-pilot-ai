"""AIAnalystService — ties `AIAnalystEngine` to the database: builds the
bounded evidence packet (Step 5/6) from `Signal` + a fresh
`TechnicalAnalysisService` snapshot + the latest `RiskEvaluation` (if
any), honors the per-signal cooldown (Step 17/25), persists the
`AIAnalysis` audit row, and translates the AI Analyst's own plain
exceptions (`ai_analyst.types`) into this app's standard error envelope
— the only piece in this package that knows about SQLAlchemy, `Signal`,
or `RiskEvaluation`.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError, ProviderError, ValidationAppError
from app.core.logging import get_logger
from app.models.ai_analysis import AIAnalysis
from app.models.risk import RiskEvaluation
from app.models.signal import Signal
from app.services.ai_analyst.engine import AIAnalystEngine
from app.services.ai_analyst.prompts import RECENT_PRICES_WINDOW
from app.services.ai_analyst.types import (
    AIAnalysisContext,
    AIProviderError,
    AIValidationError,
    FeaturesContext,
    MarketContext,
    RegimeContext,
    RiskContext,
    SignalContext,
    TechnicalContext,
)
from app.services.technical_analysis.engine import IndicatorSeries
from app.services.technical_analysis.service import TechnicalAnalysisService

logger = get_logger(__name__)


class AIAnalystService:
    def __init__(
        self,
        db: AsyncSession,
        technical_analysis_service: TechnicalAnalysisService,
        engine: AIAnalystEngine | None,
        settings: Settings,
    ) -> None:
        self.db = db
        self.technical_analysis_service = technical_analysis_service
        self.engine = engine
        self.settings = settings

    # --- status (Step 18's GET /ai/status) ------------------------------

    def get_status(self) -> dict[str, object]:
        """`available` is a proxy for `configured`, not a live
        provider ping — verifying real availability would mean an
        actual Claude call on every status check, which Step 25's cost
        controls specifically argue against."""
        return {
            "configured": self.settings.ai_configured,
            "available": self.settings.ai_configured,
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
        }

    # --- analysis --------------------------------------------------------

    async def analyze_signal(self, signal_id: uuid.UUID) -> AIAnalysis:
        started = time.monotonic()
        signal = await self._get_signal(signal_id)

        if self.engine is None:
            raise ProviderError(
                "AI provider is not configured — set AI_PROVIDER_API_KEY to enable analysis",
                details={"configured": False},
            )

        existing = await self._get_recent_analysis(signal_id)
        if existing is not None:
            existing_created_at = existing.created_at
            if existing_created_at.tzinfo is None:
                existing_created_at = existing_created_at.replace(tzinfo=UTC)
            age = datetime.now(UTC) - existing_created_at
            if age < timedelta(minutes=self.settings.ai_analyst_cooldown_minutes):
                logger.info(
                    "ai analysis deduplicated signal_id=%s analysis_id=%s age_seconds=%.0f",
                    signal_id,
                    existing.id,
                    age.total_seconds(),
                )
                return existing

        context = await self._build_context(signal)

        try:
            output = await self.engine.analyze(context)
        except AIProviderError as exc:
            duration_ms = (time.monotonic() - started) * 1000
            logger.error(
                "ai analysis provider failure signal_id=%s symbol=%s error=%s duration_ms=%.1f",
                signal_id,
                signal.asset.symbol,
                type(exc).__name__,
                duration_ms,
            )
            raise ProviderError(str(exc), details={"signal_id": str(signal_id)}) from exc
        except AIValidationError as exc:
            duration_ms = (time.monotonic() - started) * 1000
            logger.error(
                "ai analysis validation failure signal_id=%s symbol=%s reason=%s duration_ms=%.1f",
                signal_id,
                signal.asset.symbol,
                str(exc),
                duration_ms,
            )
            raise ValidationAppError(str(exc), details={"signal_id": str(signal_id)}) from exc

        row = AIAnalysis(
            signal_id=signal.id,
            asset_id=signal.asset_id,
            interval=signal.interval,
            provider=output.provider,
            model=output.model,
            prompt_version=output.prompt_version,
            market_summary=output.market_summary,
            thesis=output.thesis,
            supporting_evidence=output.supporting_evidence,
            contradicting_evidence=output.contradicting_evidence,
            risks=output.risks,
            invalidating_conditions=output.invalidating_conditions,
            suggested_action=output.suggested_action,
            action_rationale=output.action_rationale,
            uncertainty=output.uncertainty,
            model_metadata=output.model_metadata,
            generated_at=output.generated_at,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "ai analysis generated signal_id=%s analysis_id=%s symbol=%s provider=%s model=%s "
            "suggested_action=%s uncertainty=%s duration_ms=%.1f",
            signal_id,
            row.id,
            signal.asset.symbol,
            output.provider,
            output.model,
            output.suggested_action,
            output.uncertainty,
            duration_ms,
        )
        return row

    # --- reads -------------------------------------------------------------

    async def get_analysis(self, analysis_id: uuid.UUID) -> AIAnalysis:
        result = await self.db.execute(select(AIAnalysis).where(AIAnalysis.id == analysis_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(
                f"unknown AI analysis id: {analysis_id}", details={"id": str(analysis_id)}
            )
        return row

    async def list_analyses(
        self, *, symbol: str | None = None, signal_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[AIAnalysis]:
        from app.models.asset import Asset

        stmt = select(AIAnalysis)
        if symbol:
            stmt = stmt.join(AIAnalysis.asset).where(Asset.symbol == symbol.strip().upper())
        if signal_id:
            stmt = stmt.where(AIAnalysis.signal_id == signal_id)
        stmt = stmt.order_by(AIAnalysis.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_signal(self, signal_id: uuid.UUID) -> list[AIAnalysis]:
        return await self.list_analyses(signal_id=signal_id)

    # --- context assembly (Step 5/6) ----------------------------------------

    async def _build_context(self, signal: Signal) -> AIAnalysisContext:
        snapshot = await self.technical_analysis_service.get_snapshot(
            signal.asset.symbol, interval=signal.interval
        )
        series = snapshot.series
        index = snapshot.index

        recent_closes = [c for c in series.close[: index + 1] if c is not None]
        recent_prices = recent_closes[-RECENT_PRICES_WINDOW:]

        risk_row = await self._get_latest_risk_evaluation(signal.id)
        risk_context = (
            RiskContext(
                policy_version=risk_row.policy_version,
                decision=risk_row.decision,
                reasons=risk_row.reasons,
                calculated_position_size=(
                    str(risk_row.calculated_position_size)
                    if risk_row.calculated_position_size is not None
                    else None
                ),
                stop_loss_price=(
                    str(risk_row.stop_loss_price) if risk_row.stop_loss_price is not None else None
                ),
                take_profit_price=(
                    str(risk_row.take_profit_price)
                    if risk_row.take_profit_price is not None
                    else None
                ),
            )
            if risk_row is not None
            else None
        )

        return AIAnalysisContext(
            signal_id=str(signal.id),
            symbol=signal.asset.symbol,
            interval=signal.interval,
            timestamp=snapshot.calculated_at,
            market=MarketContext(
                latest_price=snapshot.latest_close,
                recent_prices=recent_prices,
                volume=_latest(series.volume, index) or 0.0,
            ),
            technical=_technical_context(series, index),
            features=FeaturesContext(
                trend_alignment_score=snapshot.features.trend_alignment_score,
                trend_alignment_label=snapshot.features.trend_alignment_label,
                trend_direction=snapshot.features.trend_direction,
                rsi_state=snapshot.features.rsi_state,
                macd_state=snapshot.features.macd_state,
                volume_state=snapshot.features.volume_state,
                volatility_state=snapshot.features.volatility_state,
            ),
            regime=RegimeContext(label=snapshot.regime.regime, reasons=snapshot.regime.reasons),
            signal=SignalContext(
                strategy_id=signal.strategy_id,
                strategy_version=signal.strategy_version,
                direction=signal.signal,
                strength=signal.strength,
                reasons=signal.reasons,
                supporting_features=signal.supporting_features,
                invalidating_conditions=signal.invalidating_conditions,
            ),
            risk=risk_context,
        )

    # --- helpers -------------------------------------------------------------

    async def _get_signal(self, signal_id: uuid.UUID) -> Signal:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()
        if signal is None:
            raise NotFoundError(f"unknown signal id: {signal_id}", details={"id": str(signal_id)})
        return signal

    async def _get_recent_analysis(self, signal_id: uuid.UUID) -> AIAnalysis | None:
        result = await self.db.execute(
            select(AIAnalysis)
            .where(AIAnalysis.signal_id == signal_id)
            .order_by(AIAnalysis.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_latest_risk_evaluation(self, signal_id: uuid.UUID) -> RiskEvaluation | None:
        result = await self.db.execute(
            select(RiskEvaluation)
            .where(RiskEvaluation.signal_id == signal_id)
            .order_by(RiskEvaluation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def _latest(series: list[float | None], index: int) -> float | None:
    return series[index] if 0 <= index < len(series) else None


def _technical_context(series: IndicatorSeries, index: int) -> TechnicalContext:
    return TechnicalContext(
        sma20=_latest(series.sma20, index),
        sma50=_latest(series.sma50, index),
        sma200=_latest(series.sma200, index),
        ema9=_latest(series.ema9, index),
        ema21=_latest(series.ema21, index),
        ema50=_latest(series.ema50, index),
        ema200=_latest(series.ema200, index),
        rsi14=_latest(series.rsi14, index),
        macd=_latest(series.macd, index),
        macd_signal=_latest(series.macd_signal, index),
        macd_histogram=_latest(series.macd_histogram, index),
        stochastic_k=_latest(series.stochastic_k, index),
        stochastic_d=_latest(series.stochastic_d, index),
        atr14=_latest(series.atr14, index),
        bollinger_upper=_latest(series.bollinger_upper, index),
        bollinger_middle=_latest(series.bollinger_middle, index),
        bollinger_lower=_latest(series.bollinger_lower, index),
        relative_volume=_latest(series.relative_volume, index),
    )
