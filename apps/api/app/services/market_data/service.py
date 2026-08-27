"""MarketDataService — the composition point for the ingestion pipeline.

Coordinates provider -> validation -> normalization -> persistence
(docs/market-data.md), and serves reads back out of Postgres. The API
layer depends only on this service; it never imports a provider or
touches the ORM directly (Step 8 of the Phase 3 plan).

Reads are "ingest-on-demand, then read from Postgres": a quote/history
request first ensures the needed range is persisted (idempotently — see
_persist), then always answers from the database, never by handing back
unpersisted provider output directly. This is what makes the API layer
and a future signal engine share one source of truth for market data,
per the architecture diagram in docs/market-data.md.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ProviderError, ValidationAppError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.market_data import SUPPORTED_INTERVALS, MarketData
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.market_data.normalizer import normalize_bar
from app.services.market_data.provider import (
    MarketDataProvider,
    ProviderBar,
    SymbolNotSupportedError,
)
from app.services.market_data.validator import validate_bar

logger = get_logger(__name__)

# Guards against a pathological date range generating an unbounded number
# of rows in one request. Not a business rule — an operational safety cap.
MAX_HISTORY_BARS = 2000

QUOTE_INTERVAL = "1m"
QUOTE_LOOKBACK = timedelta(minutes=5)


@dataclass
class IngestResult:
    requested: int
    accepted: int
    rejected: int
    rejected_reasons: list[str]


class MarketDataService:
    def __init__(self, db: AsyncSession, provider: MarketDataProvider | None = None) -> None:
        self.db = db
        self.provider = provider or MockMarketDataProvider()

    # --- assets -----------------------------------------------------

    async def list_assets(
        self, *, asset_type: str | None = None, active_only: bool = True
    ) -> list[Asset]:
        stmt = select(Asset)
        if asset_type:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if active_only:
            stmt = stmt.where(Asset.active.is_(True))
        stmt = stmt.order_by(Asset.symbol)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_asset(self, symbol: str) -> Asset:
        return await self._get_asset_by_symbol(symbol)

    async def _get_asset_by_symbol(self, symbol: str) -> Asset:
        normalized = symbol.strip().upper()
        result = await self.db.execute(select(Asset).where(Asset.symbol == normalized))
        asset = result.scalar_one_or_none()
        if asset is None:
            raise NotFoundError(f"unknown asset symbol: {symbol!r}", details={"symbol": symbol})
        return asset

    # --- ingestion ----------------------------------------------------

    async def ingest(
        self, symbol: str, *, interval: str, start: datetime, end: datetime
    ) -> IngestResult:
        if interval not in SUPPORTED_INTERVALS:
            raise ValidationAppError(
                f"unsupported interval: {interval!r}",
                details={"interval": interval, "supported": list(SUPPORTED_INTERVALS)},
            )
        if start > end:
            raise ValidationAppError(
                "start must be <= end",
                details={"start": start.isoformat(), "end": end.isoformat()},
            )

        asset = await self._get_asset_by_symbol(symbol)
        started = time.monotonic()

        try:
            raw_bars = self.provider.get_history(
                asset.symbol, start=start, end=end, interval=interval
            )
        except SymbolNotSupportedError as exc:
            raise NotFoundError(str(exc), details={"symbol": symbol}) from exc
        except Exception as exc:
            logger.error(
                "market data provider failure provider=%s symbol=%s interval=%s error=%s",
                self.provider.__class__.__name__,
                symbol,
                interval,
                exc,
            )
            raise ProviderError(f"market data provider failed: {exc}") from exc

        if len(raw_bars) > MAX_HISTORY_BARS:
            raise ValidationAppError(
                f"requested range would return {len(raw_bars)} bars, exceeding the limit of "
                f"{MAX_HISTORY_BARS}",
                details={"max_bars": MAX_HISTORY_BARS, "requested_bars": len(raw_bars)},
            )

        accepted: list[ProviderBar] = []
        rejected_count = 0
        rejected_reasons: list[str] = []
        for raw_bar in raw_bars:
            errors = validate_bar(raw_bar)
            if errors:
                # A single bar can fail multiple rules at once; it still
                # counts as one rejected record, not one per violation.
                rejected_count += 1
                rejected_reasons.extend(errors)
                continue
            accepted.append(normalize_bar(raw_bar))

        if accepted:
            await self._persist(asset.id, accepted)

        duration_ms = (time.monotonic() - started) * 1000
        logger.info(
            "market data ingestion provider=%s symbol=%s interval=%s requested=%d accepted=%d "
            "rejected=%d duration_ms=%.1f",
            self.provider.__class__.__name__,
            asset.symbol,
            interval,
            len(raw_bars),
            len(accepted),
            rejected_count,
            duration_ms,
        )

        return IngestResult(
            requested=len(raw_bars),
            accepted=len(accepted),
            rejected=rejected_count,
            rejected_reasons=rejected_reasons,
        )

    async def _persist(self, asset_id: uuid.UUID, bars: list[ProviderBar]) -> None:
        rows = [
            {
                "asset_id": asset_id,
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "source": bar.source,
                "interval": bar.interval,
            }
            for bar in bars
        ]
        stmt = pg_insert(MarketData).values(rows)
        # Idempotent ingestion (Step 9): re-ingesting an already-persisted
        # (asset_id, interval, timestamp, source) tuple is a no-op.
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["asset_id", "interval", "timestamp", "source"]
        )
        await self.db.execute(stmt)
        await self.db.commit()

    # --- reads (ingest-on-demand, then always answer from Postgres) --

    async def get_quote(
        self, symbol: str, *, as_of: datetime | None = None
    ) -> tuple[Asset, MarketData]:
        as_of = as_of or datetime.now(UTC)
        asset = await self._get_asset_by_symbol(symbol)

        await self.ingest(
            asset.symbol, interval=QUOTE_INTERVAL, start=as_of - QUOTE_LOOKBACK, end=as_of
        )

        stmt = (
            select(MarketData)
            .where(MarketData.asset_id == asset.id, MarketData.interval == QUOTE_INTERVAL)
            .order_by(MarketData.timestamp.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(
                f"no market data available for {symbol!r}", details={"symbol": symbol}
            )
        return asset, row

    async def get_history(
        self, symbol: str, *, interval: str, start: datetime, end: datetime
    ) -> tuple[Asset, list[MarketData]]:
        asset = await self._get_asset_by_symbol(symbol)
        await self.ingest(asset.symbol, interval=interval, start=start, end=end)

        stmt = (
            select(MarketData)
            .where(
                MarketData.asset_id == asset.id,
                MarketData.interval == interval,
                MarketData.timestamp >= start,
                MarketData.timestamp <= end,
            )
            .order_by(MarketData.timestamp.asc())
        )
        result = await self.db.execute(stmt)
        return asset, list(result.scalars().all())
