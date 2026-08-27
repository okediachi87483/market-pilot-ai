"""Shared types for the Risk Engine — kept in their own module so
engine.py, checks.py, and sizing.py can all depend on them without a
circular import, mirroring app/services/signal_engine/types.py.

Nothing here imports FastAPI, SQLAlchemy, or the database (Step 2): the
Risk Engine operates on plain dataclasses in, plain dataclasses out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

RiskDecision = Literal["APPROVED", "REJECTED"]

# Every name the check pipeline can report, in the exact precedence order
# documented in docs/risk-engine.md §"Check pipeline". Kept as a tuple
# (not just inline strings) so tests can assert the full pipeline shape
# in one place.
RISK_CHECK_NAMES: tuple[str, ...] = (
    "signal_validity",
    "signal_status",
    "risk_policy_enabled",
    "daily_loss_limit",
    "max_drawdown",
    "max_concurrent_positions",
    "portfolio_exposure",
    "position_size_limit",
    "stop_loss_validity",
    "take_profit_validity",
    "loss_cooldown",
)


@dataclass(frozen=True)
class RiskCheckResult:
    """One row of the audit trail (Step 6/18). `passed=False` always
    carries a human-readable `detail` explaining exactly why — never a
    bare "rejected" (Step 5). `skipped=True` means an earlier hard-gate
    check failed and this check was never meaningfully evaluable (Step 6:
    "if an earlier hard failure makes later checks unnecessary" —
    documented per-check in docs/risk-engine.md)."""

    name: str
    passed: bool
    detail: str
    skipped: bool = False


@dataclass(frozen=True)
class RiskPolicySnapshot:
    """The configured policy values the engine evaluates against — a
    plain snapshot of a `RiskPolicy` database row (app/models/risk.py),
    not the row itself, so the pure engine never touches the ORM."""

    id: uuid.UUID
    name: str
    version: int
    enabled: bool
    max_position_size_pct: Decimal
    max_portfolio_exposure_pct: Decimal
    max_daily_loss_pct: Decimal
    max_drawdown_pct: Decimal
    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    max_concurrent_positions: int
    cooldown_after_loss_minutes: int
    risk_per_trade_pct: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Authoritative portfolio state at evaluation time (Step 12/13/16:
    "the backend is authoritative", "do not use frontend state"). See
    docs/risk-engine.md §"Portfolio state" for why every field below is
    currently a clean, position-free default — Phase 7 (paper trading)
    is what will make these numbers move."""

    equity: Decimal
    cash: Decimal
    high_water_mark: Decimal
    open_position_count: int
    open_position_value: Decimal
    realized_pl_today: Decimal
    last_losing_trade_at: datetime | None
    as_of: datetime


@dataclass(frozen=True)
class RiskEvaluationOutcome:
    """The pure engine's result — everything a `RiskEvaluation` database
    row (Step 5/18) is built from, computed with zero I/O."""

    decision: RiskDecision
    checks: list[RiskCheckResult]
    reasons: list[str]
    calculated_position_size: Decimal | None
    entry_price: Decimal | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    position_value: Decimal | None
    policy_id: uuid.UUID
    policy_version: int
    portfolio_snapshot: PortfolioSnapshot
    evaluated_at: datetime
