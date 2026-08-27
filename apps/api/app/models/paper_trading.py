"""Phase 7 — paper trading. Four tables: `paper_accounts` (the single
simulated cash/equity ledger, Step 8), `paper_orders` (Step 3/4),
`paper_fills` (Step 3/6), `paper_positions` (Step 3/9/10). No real broker
identifiers, no real money anywhere in this schema — see
docs/paper-trading.md.

`current_price`, `unrealized_pnl`, and `market_value` are deliberately
NOT stored columns, despite being in Step 3's suggested position field
list — they depend on a live market price that changes continuously, so
persisting them would immediately go stale between writes. Computed on
read instead (`PaperTradingService`/`PortfolioStateProvider`), the same
choice already made for technical-analysis indicators
(docs/technical-analysis.md §10) and for Phase 6's portfolio snapshot.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.asset import Asset
from app.models.base import Base
from app.models.signal import Signal

PRICE = Numeric(20, 8)
QUANTITY = Numeric(28, 10)

ORDER_SIDES = ("BUY", "SELL")
ORDER_TYPES = ("MARKET",)
# Strict lifecycle (Step 4): PENDING is the only non-terminal state. No
# code path ever moves a FILLED/REJECTED/CANCELLED order to another
# status — enforced in PaperTradingService, not just documented here.
ORDER_STATUSES = ("PENDING", "FILLED", "REJECTED", "CANCELLED")
POSITION_STATUSES = ("OPEN", "CLOSED")


class PaperAccount(Base):
    """The one simulated account (Step 8) — matches this project's
    single-implicit-user posture (no `users`/`portfolios` table exists
    yet). Exactly one row, seeded by the initial migration from
    `RISK_STARTING_EQUITY`; nothing else ever inserts a second row.
    `cash` is the only balance directly mutated — every mutation is
    paired with a `paper_fills` row in the same transaction (Step 20),
    mirroring docs/database.md §1's `portfolios.cash` principle.
    `peak_equity` is the drawdown high-water mark (Step 15), ratcheted
    upward by `PortfolioStateProvider` whenever a new equity high is
    observed — on any read, not only on a trade, since price movement
    alone can set a new high."""

    __tablename__ = "paper_accounts"
    __table_args__ = (
        CheckConstraint("starting_equity > 0", name="ck_paper_accounts_starting_equity"),
        CheckConstraint("cash >= 0", name="ck_paper_accounts_cash_non_negative"),
        CheckConstraint("peak_equity > 0", name="ck_paper_accounts_peak_equity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    starting_equity: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    cash: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    peak_equity: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperOrder(Base):
    """One row per execution attempt (Step 3). `signal_id` is `UNIQUE`
    — the idempotency key (Step 19): a signal can produce at most one
    paper order, ever. A rejected attempt (insufficient cash, etc.)
    still gets a row with `status='REJECTED'` and `rejection_reason`
    set — an honest record of "we tried and declined," never silently
    dropped (Step 21). `signal_id` is nullable: `POST
    /paper/positions/{symbol}/close` (Step 22) creates a SELL order
    directly from a manual close action, not from a signal — Postgres's
    `UNIQUE` treats each `NULL` as distinct, so any number of
    not-signal-driven orders can coexist without violating the
    one-order-per-signal invariant."""

    __tablename__ = "paper_orders"
    __table_args__ = (
        CheckConstraint(f"side IN {ORDER_SIDES}", name="ck_paper_orders_side"),
        # A one-element Python tuple stringifies with a trailing comma
        # ("('MARKET',)"), which Postgres rejects inside IN (...) — a
        # plain equality check is both correct and simpler for a single
        # allowed value.
        CheckConstraint(f"order_type = '{ORDER_TYPES[0]}'", name="ck_paper_orders_order_type"),
        CheckConstraint(f"status IN {ORDER_STATUSES}", name="ck_paper_orders_status"),
        CheckConstraint("quantity > 0", name="ck_paper_orders_quantity_positive"),
        CheckConstraint(
            "filled_quantity >= 0 AND filled_quantity <= quantity",
            name="ck_paper_orders_filled_quantity_bounds",
        ),
        Index("ix_paper_orders_asset_id", "asset_id"),
        Index("ix_paper_orders_status", "status"),
        Index("ix_paper_orders_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default="MARKET")
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    requested_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="PENDING")
    filled_quantity: Mapped[Decimal] = mapped_column(
        QUANTITY, nullable=False, server_default=text("0")
    )
    average_fill_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped[Asset] = relationship(lazy="joined")
    signal: Mapped[Signal | None] = relationship(lazy="joined")


class PaperFill(Base):
    """One row per simulated execution (Step 3/6) — MARKET orders in
    this phase always fill completely in one fill, but the shape
    supports more than one per order without a schema change.
    `realized_pnl` is populated only for a SELL fill that reduces/closes
    a position (`NULL` for an opening/adding BUY fill) — this is what
    makes "today's realized P/L" (docs/risk-engine.md daily-loss check)
    a precise sum over fills rather than an ambiguous read of a
    cumulative position total."""

    __tablename__ = "paper_fills"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_paper_fills_quantity_positive"),
        CheckConstraint("fill_price > 0", name="ck_paper_fills_price_positive"),
        CheckConstraint("fee >= 0", name="ck_paper_fills_fee_non_negative"),
        Index("ix_paper_fills_order_id", "order_id"),
        Index("ix_paper_fills_asset_id", "asset_id"),
        Index("ix_paper_fills_timestamp", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    fee: Mapped[Decimal] = mapped_column(PRICE, nullable=False, server_default=text("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    asset: Mapped[Asset] = relationship(lazy="joined")


class PaperPosition(Base):
    """One row per asset the account has ever held (Step 3/9/10). At
    most one `OPEN` row per asset — enforced by the partial unique index
    below, not just application logic, matching the same pattern
    `risk_policies.is_active` already uses. Closed positions are kept
    (never deleted) as the historical record; a later BUY of the same
    asset opens a *new* row rather than reopening the closed one."""

    __tablename__ = "paper_positions"
    __table_args__ = (
        CheckConstraint(f"status IN {POSITION_STATUSES}", name="ck_paper_positions_status"),
        CheckConstraint("quantity >= 0", name="ck_paper_positions_quantity_non_negative"),
        Index(
            "ix_paper_positions_open_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
        Index("ix_paper_positions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(PRICE, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped[Asset] = relationship(lazy="joined")
