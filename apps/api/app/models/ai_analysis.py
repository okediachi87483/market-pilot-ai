"""Phase 8 — AI Analyst persistence (Step 15). One row per analysis run
— never overwritten, never marked "active"/"superseded" the way a
`Signal` or `RiskPolicy` is, since there is no single-current-analysis
invariant to enforce (Step 17: repeated requests within the cooldown
window return the existing row rather than creating a new one; past the
cooldown, a fresh analysis is simply a new row, and the full history
stays queryable).

**What is deliberately NOT persisted** (Step 15): no API key, no
provider credentials (never touch this table at all — they live only
in `Settings`, read from the environment). No raw prompt or raw
provider response text — only `model_metadata` (stop reason, token
counts), which is useful for cost/debugging without storing
potentially-large free-form text twice (it's already fully captured,
field by field, in the columns below).
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.asset import Asset
from app.models.base import Base
from app.models.signal import Signal

SUGGESTED_ACTIONS = ("BUY", "SELL", "HOLD", "NO_ACTION")
UNCERTAINTY_LEVELS = ("LOW", "MEDIUM", "HIGH")


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        CheckConstraint(f"suggested_action IN {SUGGESTED_ACTIONS}", name="ck_ai_analyses_action"),
        CheckConstraint(f"uncertainty IN {UNCERTAINTY_LEVELS}", name="ck_ai_analyses_uncertainty"),
        Index("ix_ai_analyses_signal_id", "signal_id"),
        Index("ix_ai_analyses_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)

    market_summary: Mapped[str] = mapped_column(Text, nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    contradicting_evidence: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    risks: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    invalidating_conditions: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    suggested_action: Mapped[str] = mapped_column(String(10), nullable=False)
    action_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty: Mapped[str] = mapped_column(String(10), nullable=False)
    model_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal: Mapped[Signal] = relationship(lazy="joined")
    asset: Mapped[Asset] = relationship(lazy="joined")
