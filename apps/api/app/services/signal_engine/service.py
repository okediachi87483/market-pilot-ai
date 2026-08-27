"""SignalService — ties TechnicalAnalysisService to SignalEngine and
persistence, including the cooldown/deduplication rule (Step 9). The
Signal Engine itself (engine.py) never touches the database or knows
this service exists; this is the only place a `SignalCandidate` becomes
a persisted `Signal` row.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.signal import Signal
from app.services.signal_engine.engine import SignalEngine
from app.services.signal_engine.types import SignalCandidate, SignalInput
from app.services.technical_analysis.service import TechnicalAnalysisService

logger = get_logger(__name__)

# How long a CANDIDATE with an unchanged signal type suppresses a new row
# on re-evaluation (Step 9: "AAPL BUY four times a minute apart shouldn't
# become four meaningful signals"). A single process-local constant, not
# a distributed rate limiter — see docs/signal-engine.md
# §"Cooldown / deduplication" for the full rationale.
COOLDOWN = timedelta(minutes=15)


class SignalService:
    def __init__(
        self, db: AsyncSession, technical_analysis_service: TechnicalAnalysisService
    ) -> None:
        self.db = db
        self.technical_analysis_service = technical_analysis_service
        self.engine = SignalEngine()

    async def evaluate(
        self, symbol: str, *, interval: str = "1h", end: datetime | None = None
    ) -> tuple[Signal, bool]:
        """Evaluate `symbol` as of `end` (default: now) and persist the
        result, honoring the cooldown/dedup rule. Returns (signal_row,
        was_newly_created) — `was_newly_created=False` means an existing,
        still-fresh CANDIDATE was returned unchanged rather than
        inserting a duplicate. `end` is exposed mainly for deterministic
        testing (and future backtesting reuse) — the API never passes it,
        always evaluating as of now."""
        started = time.monotonic()
        snapshot = await self.technical_analysis_service.get_snapshot(
            symbol, interval=interval, end=end
        )

        signal_input = SignalInput(
            symbol=snapshot.asset.symbol,
            interval=interval,
            timestamp=snapshot.calculated_at,
            candle_count=snapshot.candle_count,
            regime=snapshot.regime,
            features=snapshot.features,
            rsi14=snapshot.series.rsi14[snapshot.index],
        )
        candidate = self.engine.evaluate(signal_input)

        row, created = await self._persist(snapshot.asset, interval, candidate)

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "signal evaluated symbol=%s interval=%s strategy=%s strategy_version=%s "
            "signal=%s strength=%s regime=%s created=%s duration_ms=%.1f",
            candidate.symbol,
            interval,
            candidate.strategy_id,
            candidate.strategy_version,
            candidate.signal,
            candidate.strength,
            candidate.market_regime,
            created,
            duration_ms,
        )
        return row, created

    async def _persist(
        self, asset: Asset, interval: str, candidate: SignalCandidate
    ) -> tuple[Signal, bool]:
        stmt = (
            select(Signal)
            .where(
                Signal.asset_id == asset.id,
                Signal.interval == interval,
                Signal.strategy_id == candidate.strategy_id,
                Signal.strategy_version == candidate.strategy_version,
                Signal.status == "CANDIDATE",
            )
            .order_by(Signal.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        now = datetime.now(UTC)
        if existing is not None and existing.signal == candidate.signal:
            existing_created_at = existing.created_at
            if existing_created_at.tzinfo is None:
                existing_created_at = existing_created_at.replace(tzinfo=UTC)
            age = now - existing_created_at
            if age < COOLDOWN:
                logger.info(
                    "signal deduplicated symbol=%s interval=%s strategy=%s signal=%s "
                    "existing_id=%s age_seconds=%.0f",
                    candidate.symbol,
                    interval,
                    candidate.strategy_id,
                    candidate.signal,
                    existing.id,
                    age.total_seconds(),
                )
                return existing, False

        if existing is not None:
            existing.status = "SUPERSEDED"

        row = Signal(
            asset_id=asset.id,
            interval=interval,
            signal=candidate.signal,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            strength=candidate.strength,
            market_regime=candidate.market_regime,
            reasons=candidate.reasons,
            supporting_features=candidate.supporting_features,
            invalidating_conditions=candidate.invalidating_conditions,
            status="CANDIDATE",
            generated_at=candidate.timestamp,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row, True

    async def get_signal(self, signal_id: uuid.UUID) -> Signal:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"unknown signal id: {signal_id}", details={"id": str(signal_id)})
        return row

    async def list_signals(
        self,
        *,
        symbol: str | None = None,
        strategy_id: str | None = None,
        status: str | None = None,
        interval: str | None = None,
        limit: int = 50,
    ) -> list[Signal]:
        stmt = select(Signal).join(Signal.asset)
        if symbol:
            stmt = stmt.where(Asset.symbol == symbol.strip().upper())
        if strategy_id:
            stmt = stmt.where(Signal.strategy_id == strategy_id)
        if status:
            stmt = stmt.where(Signal.status == status)
        if interval:
            stmt = stmt.where(Signal.interval == interval)
        stmt = stmt.order_by(Signal.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
