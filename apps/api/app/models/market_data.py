import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy import DateTime as SA_DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Kept in sync with the CHECK constraint added in the Alembic migration.
SUPPORTED_INTERVALS = ("1m", "5m", "15m", "1h", "1d")

# Price precision matches docs/database.md §1 — NUMERIC, never float.
PRICE = Numeric(20, 8)
QUANTITY = Numeric(28, 10)


class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = (
        # Idempotent ingestion: re-ingesting the same bar from the same
        # source is a no-op, not a duplicate row. See docs/market-data.md.
        UniqueConstraint(
            "asset_id",
            "interval",
            "timestamp",
            "source",
            name="uq_market_data_asset_interval_ts_source",
        ),
        Index("ix_market_data_asset_timestamp", "asset_id", "timestamp"),
        CheckConstraint(f"interval IN {SUPPORTED_INTERVALS}", name="ck_market_data_interval"),
        CheckConstraint("high >= open", name="ck_market_data_high_gte_open"),
        CheckConstraint("high >= close", name="ck_market_data_high_gte_close"),
        CheckConstraint("high >= low", name="ck_market_data_high_gte_low"),
        CheckConstraint("low <= open", name="ck_market_data_low_lte_open"),
        CheckConstraint("low <= close", name="ck_market_data_low_lte_close"),
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_market_data_prices_positive"
        ),
        CheckConstraint("volume >= 0", name="ck_market_data_volume_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        SA_DateTime(timezone=True), nullable=False, index=True
    )
    open: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    high: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    low: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    close: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    volume: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        SA_DateTime(timezone=True), server_default=func.now()
    )
