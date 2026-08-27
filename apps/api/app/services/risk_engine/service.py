"""RiskService — ties `RiskEngine` to the database: fetches the active
policy and current portfolio snapshot, calls the pure engine, persists
the `RiskEvaluation` audit row, and performs the one controlled signal
status transition this phase allows (`CANDIDATE` -> `RISK_APPROVED` /
`RISK_REJECTED`, Step 17). The `RiskEngine` itself never touches the
database or knows this service exists — mirrors `SignalService`'s
relationship to `SignalEngine` (Phase 5).
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal
from app.services.market_data.service import MarketDataService
from app.services.risk_engine.engine import RiskEngine
from app.services.risk_engine.portfolio_state import PortfolioStateProvider
from app.services.risk_engine.types import PortfolioSnapshot, RiskPolicySnapshot
from app.services.signal_engine.risk_boundary import to_risk_evaluation_request_from_signal

logger = get_logger(__name__)


class RiskService:
    def __init__(
        self,
        db: AsyncSession,
        market_data_service: MarketDataService,
        portfolio_state_provider: PortfolioStateProvider,
    ) -> None:
        self.db = db
        self.market_data_service = market_data_service
        self.portfolio_state_provider = portfolio_state_provider
        self.engine = RiskEngine()

    # --- policy ---------------------------------------------------

    async def get_active_policy(self) -> RiskPolicy:
        result = await self.db.execute(select(RiskPolicy).where(RiskPolicy.is_active.is_(True)))
        policy = result.scalar_one_or_none()
        if policy is None:
            # Should never happen — the initial migration seeds exactly
            # one active policy, and update_policy() always preserves
            # that invariant inside one transaction. Surfacing this as a
            # clear 500 rather than silently approving anything.
            raise AppError("no active risk policy is configured")
        return policy

    async def update_policy(self, updates: dict[str, Decimal | int | bool]) -> RiskPolicy:
        """Creates a new, incremented-version policy row and activates
        it; the previous active row is deactivated but never deleted or
        mutated (Step 4/24: policy version is preserved for every past
        evaluation that referenced it). All fields are required — see
        docs/api.md `PUT /risk/rules` for why partial updates aren't
        supported for a safety-critical configuration."""
        current = await self.get_active_policy()
        current.is_active = False
        await self.db.flush()  # the old row's UPDATE must land before the new row's INSERT
        # (both is_active=True at once would violate the partial unique index).

        new_policy = RiskPolicy(
            name=current.name,
            version=current.version + 1,
            is_active=True,
            **updates,
        )
        self.db.add(new_policy)
        await self.db.commit()
        await self.db.refresh(new_policy)
        logger.info(
            "risk policy updated name=%s new_version=%d previous_version=%d",
            new_policy.name,
            new_policy.version,
            current.version,
        )
        return new_policy

    def _to_policy_snapshot(self, row: RiskPolicy) -> RiskPolicySnapshot:
        return RiskPolicySnapshot(
            id=row.id,
            name=row.name,
            version=row.version,
            enabled=row.enabled,
            max_position_size_pct=row.max_position_size_pct,
            max_portfolio_exposure_pct=row.max_portfolio_exposure_pct,
            max_daily_loss_pct=row.max_daily_loss_pct,
            max_drawdown_pct=row.max_drawdown_pct,
            stop_loss_pct=row.stop_loss_pct,
            take_profit_pct=row.take_profit_pct,
            max_concurrent_positions=row.max_concurrent_positions,
            cooldown_after_loss_minutes=row.cooldown_after_loss_minutes,
            risk_per_trade_pct=row.risk_per_trade_pct,
        )

    # --- portfolio --------------------------------------------------

    async def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        return await self.portfolio_state_provider.get_snapshot()

    # --- evaluation ---------------------------------------------------

    async def evaluate_signal(self, signal_id: uuid.UUID) -> RiskEvaluation:
        started = time.monotonic()

        # Provisional, *unlocked* fetch: fails fast on a non-CANDIDATE
        # signal without bothering to fetch a quote, but MUST NOT be the
        # check this method actually relies on for correctness — see
        # below. `RiskEvaluation.signal_id` has no unique constraint
        # (unlike `paper_orders.signal_id`), so nothing at the database
        # level backstops "only one evaluation, ever" — the lock
        # acquired further down is the only thing that does.
        provisional_signal = await self._get_signal(signal_id)
        if provisional_signal.status != "CANDIDATE":
            raise ConflictError(
                f"signal {signal_id} is already {provisional_signal.status!r} — only a "
                "CANDIDATE signal may be risk-evaluated (re-evaluation is not supported in "
                "this phase)",
                details={"signal_id": str(signal_id), "status": provisional_signal.status},
            )

        policy_row = await self.get_active_policy()
        policy_snapshot = self._to_policy_snapshot(policy_row)
        portfolio = await self.portfolio_state_provider.get_snapshot()

        # get_quote() eagerly persists (and *commits*) any freshly-ingested
        # market data — a commit ends the current transaction and would
        # release any row lock taken before this point. Deliberately
        # called before the locked re-check below, not after, so the lock
        # is acquired last and held continuously through to commit()
        # (tests/test_risk_concurrency.py catches the ordering mistake).
        _asset, market_data_row = await self.market_data_service.get_quote(
            provisional_signal.asset.symbol
        )
        entry_price = market_data_row.close

        # Authoritative, locked re-check: two concurrent calls can both
        # pass the provisional check above before either commits: without
        # this lock, both proceed to evaluate, both INSERT a
        # RiskEvaluation, and whichever COMMITs last silently overwrites
        # the signal's status — two audit rows for one signal, not just a
        # duplicate. The lock makes the second request block until the
        # first's transaction ends, then re-read the *real* current
        # status (no longer CANDIDATE) instead of a stale copy.
        signal = await self._get_signal_for_update(signal_id)
        if signal.status != "CANDIDATE":
            raise ConflictError(
                f"signal {signal_id} is already {signal.status!r} — only a CANDIDATE signal "
                "may be risk-evaluated (re-evaluation is not supported in this phase)",
                details={"signal_id": str(signal_id), "status": signal.status},
            )

        request = to_risk_evaluation_request_from_signal(signal)
        now = datetime.now(UTC)
        outcome = self.engine.evaluate(
            request, policy=policy_snapshot, portfolio=portfolio, entry_price=entry_price, now=now
        )

        evaluation = RiskEvaluation(
            signal_id=signal.id,
            policy_id=outcome.policy_id,
            policy_version=outcome.policy_version,
            decision=outcome.decision,
            reasons=outcome.reasons,
            checks=[dataclasses.asdict(c) for c in outcome.checks],
            calculated_position_size=outcome.calculated_position_size,
            entry_price=outcome.entry_price,
            stop_loss_price=outcome.stop_loss_price,
            take_profit_price=outcome.take_profit_price,
            position_value=outcome.position_value,
            portfolio_snapshot=_snapshot_to_json(outcome.portfolio_snapshot),
            evaluated_at=outcome.evaluated_at,
        )
        self.db.add(evaluation)
        signal.status = "RISK_APPROVED" if outcome.decision == "APPROVED" else "RISK_REJECTED"
        await self.db.commit()
        await self.db.refresh(evaluation)

        duration_ms = (time.monotonic() - started) * 1000
        failed_checks = [c.name for c in outcome.checks if not c.passed]
        logger.info(
            "risk evaluation signal_id=%s symbol=%s policy_version=%d decision=%s "
            "failed_checks=%s duration_ms=%.1f",
            signal.id,
            request.symbol,
            outcome.policy_version,
            outcome.decision,
            ",".join(failed_checks) if failed_checks else "-",
            duration_ms,
        )
        return evaluation

    async def _get_signal(self, signal_id: uuid.UUID) -> Signal:
        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        signal = result.scalar_one_or_none()
        if signal is None:
            raise NotFoundError(f"unknown signal id: {signal_id}", details={"id": str(signal_id)})
        return signal

    async def _get_signal_for_update(self, signal_id: uuid.UUID) -> Signal:
        # `of=Signal`: Signal.asset is `lazy="joined"` (a LEFT OUTER
        # JOIN) — plain FOR UPDATE can't lock across the nullable side of
        # an outer join, so the lock is scoped to just this table.
        #
        # `populate_existing()` is not optional here: `evaluate_signal`
        # already loaded this same row (unlocked) into this session's
        # identity map a few lines earlier (`provisional_signal`). By
        # default SQLAlchemy does NOT overwrite an already-identity-mapped
        # object's attributes from a later query's result — it silently
        # returns the *same stale Python object* even though the SQL sent
        # to Postgres genuinely blocked, locked, and re-fetched the
        # current row. Without this, `signal.status` here would still
        # read the pre-lock "CANDIDATE" value forever, and the
        # `!= "CANDIDATE"` guard below would never fire — confirmed
        # directly: tests/test_risk_concurrency.py failed with this
        # exact symptom (two evaluations created) until this was added.
        result = await self.db.execute(
            select(Signal)
            .where(Signal.id == signal_id)
            .with_for_update(of=Signal)
            .execution_options(populate_existing=True)
        )
        signal = result.scalar_one_or_none()
        if signal is None:
            raise NotFoundError(f"unknown signal id: {signal_id}", details={"id": str(signal_id)})
        return signal

    async def get_evaluation(self, evaluation_id: uuid.UUID) -> RiskEvaluation:
        result = await self.db.execute(
            select(RiskEvaluation).where(RiskEvaluation.id == evaluation_id)
        )
        evaluation = result.scalar_one_or_none()
        if evaluation is None:
            raise NotFoundError(
                f"unknown risk evaluation id: {evaluation_id}",
                details={"id": str(evaluation_id)},
            )
        return evaluation

    async def list_evaluations(
        self,
        *,
        signal_id: uuid.UUID | None = None,
        decision: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[RiskEvaluation]:
        stmt = select(RiskEvaluation)
        if signal_id:
            stmt = stmt.where(RiskEvaluation.signal_id == signal_id)
        if decision:
            stmt = stmt.where(RiskEvaluation.decision == decision)
        if symbol:
            stmt = stmt.join(RiskEvaluation.signal).join(Signal.asset)
            from app.models.asset import Asset

            stmt = stmt.where(Asset.symbol == symbol.strip().upper())
        stmt = stmt.order_by(RiskEvaluation.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


def _snapshot_to_json(snapshot: PortfolioSnapshot) -> dict[str, object]:
    """`PortfolioSnapshot` holds `Decimal`/`datetime` fields that aren't
    natively JSON-serializable — converted to strings/ISO timestamps for
    the `portfolio_snapshot` JSONB audit column (Step 18)."""
    data = dataclasses.asdict(snapshot)
    for key in ("equity", "cash", "high_water_mark", "open_position_value", "realized_pl_today"):
        data[key] = str(data[key])
    data["as_of"] = snapshot.as_of.isoformat()
    data["last_losing_trade_at"] = (
        snapshot.last_losing_trade_at.isoformat() if snapshot.last_losing_trade_at else None
    )
    return data
