import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Kept in sync with the CHECK constraint added in the Alembic migration —
# SQLAlchemy does not enforce Python-level enums at the DB layer here, the
# migration's CHECK does.
ASSET_TYPES = ("equity", "etf", "crypto", "forex")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("symbol", "asset_type", name="uq_assets_symbol_asset_type"),
        CheckConstraint(
            f"asset_type IN {ASSET_TYPES}",
            name="ck_assets_asset_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="USD")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
