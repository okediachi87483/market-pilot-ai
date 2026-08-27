import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.asset import Asset
from app.models.base import Base

# Kept in sync with the CHECK constraints added in the Alembic migration.
SIGNAL_TYPES = ("BUY", "SELL", "HOLD")
SIGNAL_STRENGTHS = ("WEAK", "MODERATE", "STRONG")
# The Signal Engine itself only ever writes CANDIDATE (Step 10) — the
# other statuses are written by the future Risk Engine (RISK_APPROVED/
# RISK_REJECTED), a future expiry job (EXPIRED), or this service's own
# dedup/cooldown logic superseding a stale candidate (SUPERSEDED). See
# docs/signal-engine.md §"Signal lifecycle".
SIGNAL_STATUSES = ("CANDIDATE", "RISK_APPROVED", "RISK_REJECTED", "EXPIRED", "SUPERSEDED")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(f"signal IN {SIGNAL_TYPES}", name="ck_signals_signal"),
        CheckConstraint(
            f"strength IS NULL OR strength IN {SIGNAL_STRENGTHS}", name="ck_signals_strength"
        ),
        CheckConstraint(f"status IN {SIGNAL_STATUSES}", name="ck_signals_status"),
        Index("ix_signals_lookup", "asset_id", "interval", "strategy_id", "status"),
        Index("ix_signals_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    signal: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(10), nullable=True)
    market_regime: Mapped[str] = mapped_column(String(20), nullable=False)
    # JSONB on Postgres; JSON is the SQLAlchemy-portable fallback type for
    # any other dialect a future test setup might use.
    reasons: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    supporting_features: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    invalidating_conditions: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="CANDIDATE")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship(lazy="joined")
