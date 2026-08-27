import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.signal import Signal

PCT = Numeric(5, 2)
PRICE = Numeric(20, 8)
QUANTITY = Numeric(28, 10)

RISK_DECISIONS = ("APPROVED", "REJECTED")


class RiskPolicy(Base):
    """A named, versioned risk configuration (Step 4). Rows are
    immutable once created — `RiskService.update_policy()` never UPDATEs
    an existing row's numbers; it inserts a new version, deactivates the
    old one, and activates the new one. This is what makes
    `RiskEvaluation.policy_version` (Step 18/24) a meaningful, permanent
    pointer to the exact numbers a past evaluation used, without a
    separate snapshot column. See docs/risk-engine.md §"Policy
    versioning"."""

    __tablename__ = "risk_policies"
    __table_args__ = (
        CheckConstraint(
            "max_position_size_pct > 0 AND max_position_size_pct <= 100",
            name="ck_risk_policies_max_position_size_pct",
        ),
        CheckConstraint(
            "max_portfolio_exposure_pct > 0 AND max_portfolio_exposure_pct <= 100",
            name="ck_risk_policies_max_portfolio_exposure_pct",
        ),
        CheckConstraint(
            "max_daily_loss_pct > 0 AND max_daily_loss_pct <= 100",
            name="ck_risk_policies_max_daily_loss_pct",
        ),
        CheckConstraint(
            "max_drawdown_pct > 0 AND max_drawdown_pct <= 100",
            name="ck_risk_policies_max_drawdown_pct",
        ),
        CheckConstraint(
            "stop_loss_pct > 0 AND stop_loss_pct < 100", name="ck_risk_policies_stop_loss_pct"
        ),
        CheckConstraint(
            "take_profit_pct > 0 AND take_profit_pct <= 1000",
            name="ck_risk_policies_take_profit_pct",
        ),
        CheckConstraint(
            "risk_per_trade_pct > 0 AND risk_per_trade_pct <= 100",
            name="ck_risk_policies_risk_per_trade_pct",
        ),
        CheckConstraint(
            "max_concurrent_positions >= 1 AND max_concurrent_positions <= 1000",
            name="ck_risk_policies_max_concurrent_positions",
        ),
        CheckConstraint(
            "cooldown_after_loss_minutes >= 0 AND cooldown_after_loss_minutes <= 10080",
            name="ck_risk_policies_cooldown_after_loss_minutes",
        ),
        UniqueConstraint("name", "version", name="uq_risk_policies_name_version"),
        # Exactly one active policy at a time (Step 4: "a clear concept
        # of the currently active policy") — a partial unique index, not
        # an application-level check, so it holds even under a race.
        Index(
            "ix_risk_policies_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    max_position_size_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    max_portfolio_exposure_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    max_drawdown_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    stop_loss_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    take_profit_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    risk_per_trade_pct: Mapped[Decimal] = mapped_column(PCT, nullable=False)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_after_loss_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiskEvaluation(Base):
    """The audit trail for one risk decision (Step 5/18). One row per
    call to `POST /risk/evaluate/{signal_id}` — never updated after
    insert, mirroring `audit_logs`' append-only posture
    (docs/database.md §1)."""

    __tablename__ = "risk_evaluations"
    __table_args__ = (
        CheckConstraint(f"decision IN {RISK_DECISIONS}", name="ck_risk_evaluations_decision"),
        Index("ix_risk_evaluations_signal_id", "signal_id"),
        Index("ix_risk_evaluations_created_at", "created_at"),
        Index("ix_risk_evaluations_decision", "decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_policies.id"), nullable=False
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    checks: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    calculated_position_size: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    entry_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    position_value: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    portfolio_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),  # type: ignore[no-untyped-call]
        nullable=False,
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal: Mapped[Signal] = relationship(lazy="joined")
