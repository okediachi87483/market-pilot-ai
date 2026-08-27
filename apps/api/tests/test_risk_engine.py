"""End-to-end tests for app/services/risk_engine/engine.py — the pure
`RiskEngine.evaluate()` orchestration (sizing + checks -> outcome).
Also the invariant tests required by Step 26."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.risk_engine.engine import RiskEngine
from app.services.risk_engine.types import PortfolioSnapshot, RiskPolicySnapshot
from app.services.signal_engine.risk_boundary import RiskEvaluationRequest

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _request(**overrides) -> RiskEvaluationRequest:
    fields = dict(
        signal_id=uuid.uuid4(),
        symbol="AAPL",
        signal="BUY",
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG",
        reasons=["Detected market regime is BULLISH"],
        supporting_features={"rsi14": 55.0},
        invalidating_conditions=["MACD turns bearish"],
    )
    fields.update(overrides)
    return RiskEvaluationRequest(**fields)


def _policy(**overrides) -> RiskPolicySnapshot:
    fields = dict(
        id=uuid.uuid4(),
        name="default",
        version=1,
        enabled=True,
        max_position_size_pct=Decimal("5.00"),
        max_portfolio_exposure_pct=Decimal("50.00"),
        max_daily_loss_pct=Decimal("3.00"),
        max_drawdown_pct=Decimal("15.00"),
        stop_loss_pct=Decimal("2.00"),
        take_profit_pct=Decimal("4.00"),
        max_concurrent_positions=5,
        cooldown_after_loss_minutes=60,
        risk_per_trade_pct=Decimal("1.00"),
    )
    fields.update(overrides)
    return RiskPolicySnapshot(**fields)


def _portfolio(**overrides) -> PortfolioSnapshot:
    fields = dict(
        equity=Decimal("100000"),
        cash=Decimal("100000"),
        high_water_mark=Decimal("100000"),
        open_position_count=0,
        open_position_value=Decimal("0"),
        realized_pl_today=Decimal("0"),
        last_losing_trade_at=None,
        as_of=NOW,
    )
    fields.update(overrides)
    return PortfolioSnapshot(**fields)


def test_healthy_buy_candidate_is_approved():
    outcome = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    assert outcome.decision == "APPROVED"
    assert outcome.reasons == []
    assert outcome.calculated_position_size is not None
    assert outcome.calculated_position_size > 0


def test_sell_signal_is_rejected_with_a_reason():
    outcome = RiskEngine().evaluate(
        _request(signal="SELL"),
        policy=_policy(),
        portfolio=_portfolio(),
        entry_price=Decimal("100.00"),
        now=NOW,
    )
    assert outcome.decision == "REJECTED"
    assert len(outcome.reasons) >= 1


def test_disabled_policy_rejects_even_a_healthy_candidate():
    outcome = RiskEngine().evaluate(
        _request(),
        policy=_policy(enabled=False),
        portfolio=_portfolio(),
        entry_price=Decimal("100.00"),
        now=NOW,
    )
    assert outcome.decision == "REJECTED"


def test_outcome_preserves_policy_id_and_version():
    policy = _policy(version=7)
    outcome = RiskEngine().evaluate(
        _request(), policy=policy, portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    assert outcome.policy_id == policy.id
    assert outcome.policy_version == 7


def test_evaluation_is_deterministic():
    first = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("173.45"), now=NOW
    )
    second = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("173.45"), now=NOW
    )
    assert first.decision == second.decision
    assert first.calculated_position_size == second.calculated_position_size
    assert first.stop_loss_price == second.stop_loss_price
    assert first.take_profit_price == second.take_profit_price
    assert [c.detail for c in first.checks] == [c.detail for c in second.checks]


# --- invariants (Step 26) ----------------------------------------------------


def test_invariant_approval_always_has_a_valid_positive_position_size():
    outcome = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    if outcome.decision == "APPROVED":
        assert outcome.calculated_position_size is not None
        assert outcome.calculated_position_size > 0


def test_invariant_approved_buy_always_has_a_valid_stop_loss():
    outcome = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    if outcome.decision == "APPROVED":
        assert outcome.stop_loss_price is not None
        assert outcome.stop_loss_price > 0
        assert outcome.stop_loss_price < outcome.entry_price


def test_invariant_approved_buy_always_has_a_valid_take_profit():
    outcome = RiskEngine().evaluate(
        _request(), policy=_policy(), portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    if outcome.decision == "APPROVED":
        assert outcome.take_profit_price is not None
        assert outcome.take_profit_price > outcome.entry_price


def test_invariant_approved_trade_never_exceeds_max_exposure():
    policy = _policy(max_portfolio_exposure_pct=Decimal("50.00"))
    portfolio = _portfolio(open_position_value=Decimal("10000"))
    outcome = RiskEngine().evaluate(
        _request(), policy=policy, portfolio=portfolio, entry_price=Decimal("100.00"), now=NOW
    )
    if outcome.decision == "APPROVED":
        max_exposure = portfolio.equity * policy.max_portfolio_exposure_pct / Decimal("100")
        total_exposure = portfolio.open_position_value + (outcome.position_value or Decimal("0"))
        assert total_exposure <= max_exposure


def test_invariant_approved_trade_never_exceeds_max_position_size():
    policy = _policy(max_position_size_pct=Decimal("5.00"))
    portfolio = _portfolio()
    outcome = RiskEngine().evaluate(
        _request(), policy=policy, portfolio=portfolio, entry_price=Decimal("100.00"), now=NOW
    )
    if outcome.decision == "APPROVED":
        max_position_value = portfolio.equity * policy.max_position_size_pct / Decimal("100")
        assert (outcome.position_value or Decimal("0")) <= max_position_value


def test_invariant_rejection_always_has_at_least_one_reason():
    outcome = RiskEngine().evaluate(
        _request(signal="HOLD"),
        policy=_policy(),
        portfolio=_portfolio(),
        entry_price=Decimal("100.00"),
        now=NOW,
    )
    assert outcome.decision == "REJECTED"
    assert len(outcome.reasons) >= 1


def test_invariant_policy_version_is_preserved_on_both_outcomes():
    policy = _policy(version=3)
    approved = RiskEngine().evaluate(
        _request(), policy=policy, portfolio=_portfolio(), entry_price=Decimal("100.00"), now=NOW
    )
    rejected = RiskEngine().evaluate(
        _request(signal="HOLD"),
        policy=policy,
        portfolio=_portfolio(),
        entry_price=Decimal("100.00"),
        now=NOW,
    )
    assert approved.policy_version == 3
    assert rejected.policy_version == 3


def test_invariant_identical_input_produces_identical_output():
    request = _request()
    policy = _policy()
    portfolio = _portfolio()
    engine = RiskEngine()

    outcomes = [
        engine.evaluate(
            request, policy=policy, portfolio=portfolio, entry_price=Decimal("55.55"), now=NOW
        )
        for _ in range(3)
    ]
    decisions = {o.decision for o in outcomes}
    sizes = {o.calculated_position_size for o in outcomes}
    assert len(decisions) == 1
    assert len(sizes) == 1


def test_invariant_engine_never_sets_a_status_other_than_approved_or_rejected():
    for signal_type in ("BUY", "SELL", "HOLD"):
        outcome = RiskEngine().evaluate(
            _request(signal=signal_type),
            policy=_policy(),
            portfolio=_portfolio(),
            entry_price=Decimal("100.00"),
            now=NOW,
        )
        assert outcome.decision in ("APPROVED", "REJECTED")
