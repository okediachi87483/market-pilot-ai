"""Unit tests for app/services/risk_engine/checks.py — the 11-check
pipeline (Step 6), in precedence order. Pure functions, no database."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.risk_engine.checks import evaluate_checks
from app.services.risk_engine.types import RISK_CHECK_NAMES, PortfolioSnapshot, RiskPolicySnapshot
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


def _run(
    *,
    request=None,
    policy=None,
    portfolio=None,
    entry_price=Decimal("100.00"),
    stop_loss_price=Decimal("98.00"),
    take_profit_price=Decimal("104.00"),
    quantity=Decimal("10"),
    position_value=Decimal("1000"),
    now=NOW,
):
    return evaluate_checks(
        request=request or _request(),
        policy=policy or _policy(),
        portfolio=portfolio or _portfolio(),
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        quantity=quantity,
        position_value=position_value,
        now=now,
    )


def test_check_names_always_match_the_documented_order():
    results = _run()
    assert tuple(c.name for c in results) == RISK_CHECK_NAMES


def test_all_checks_pass_for_a_healthy_candidate():
    results = _run()
    assert all(c.passed for c in results)


# --- 1. signal validity --------------------------------------------------


def test_sell_signal_fails_signal_validity_and_skips_the_rest():
    results = _run(request=_request(signal="SELL"))
    assert results[0].name == "signal_validity"
    assert results[0].passed is False
    assert results[0].skipped is False
    assert all(c.skipped for c in results[1:])


def test_hold_signal_fails_signal_validity():
    results = _run(request=_request(signal="HOLD"))
    assert results[0].passed is False


# --- 3. risk policy enabled ------------------------------------------------


def test_disabled_policy_fails_and_skips_checks_4_through_11():
    results = _run(policy=_policy(enabled=False))
    by_name = {c.name: c for c in results}
    assert by_name["signal_validity"].passed is True
    assert by_name["signal_status"].passed is True
    assert by_name["risk_policy_enabled"].passed is False
    assert by_name["risk_policy_enabled"].skipped is False
    for name in RISK_CHECK_NAMES[3:]:
        assert by_name[name].skipped is True


# --- 4. daily loss limit ----------------------------------------------------


def test_daily_loss_within_limit_passes():
    results = _run(portfolio=_portfolio(realized_pl_today=Decimal("-2000")))  # -2% of 100000
    assert _check(results, "daily_loss_limit").passed is True


def test_daily_loss_exactly_at_limit_fails():
    # max_daily_loss_pct=3% of 100000 = -3000; "at or beyond" the floor fails.
    results = _run(portfolio=_portfolio(realized_pl_today=Decimal("-3000")))
    assert _check(results, "daily_loss_limit").passed is False


def test_daily_loss_just_below_limit_passes():
    results = _run(portfolio=_portfolio(realized_pl_today=Decimal("-2999.99")))
    assert _check(results, "daily_loss_limit").passed is True


def test_daily_loss_beyond_limit_fails():
    results = _run(portfolio=_portfolio(realized_pl_today=Decimal("-5000")))
    assert _check(results, "daily_loss_limit").passed is False


# --- 5. max drawdown ---------------------------------------------------------


def test_drawdown_within_limit_passes():
    results = _run(
        portfolio=_portfolio(high_water_mark=Decimal("100000"), equity=Decimal("90000"))
    )  # 10% drawdown, limit 15%
    assert _check(results, "max_drawdown").passed is True


def test_drawdown_at_limit_fails():
    results = _run(
        portfolio=_portfolio(high_water_mark=Decimal("100000"), equity=Decimal("85000"))
    )  # exactly 15%
    assert _check(results, "max_drawdown").passed is False


def test_drawdown_just_below_limit_passes():
    results = _run(
        portfolio=_portfolio(high_water_mark=Decimal("100000"), equity=Decimal("85000.01"))
    )
    assert _check(results, "max_drawdown").passed is True


def test_non_positive_high_water_mark_fails_closed():
    results = _run(portfolio=_portfolio(high_water_mark=Decimal("0")))
    assert _check(results, "max_drawdown").passed is False


def test_negative_high_water_mark_fails_closed_without_dividing_by_zero():
    results = _run(portfolio=_portfolio(high_water_mark=Decimal("-100")))
    assert _check(results, "max_drawdown").passed is False


# --- 6. max concurrent positions ---------------------------------------------


def test_concurrent_positions_within_limit_passes():
    results = _run(
        policy=_policy(max_concurrent_positions=5), portfolio=_portfolio(open_position_count=3)
    )
    assert _check(results, "max_concurrent_positions").passed is True


def test_concurrent_positions_at_limit_fails():
    # 5 open + this candidate = 6 > limit of 5.
    results = _run(
        policy=_policy(max_concurrent_positions=5), portfolio=_portfolio(open_position_count=5)
    )
    assert _check(results, "max_concurrent_positions").passed is False


def test_concurrent_positions_just_below_limit_passes():
    results = _run(
        policy=_policy(max_concurrent_positions=5), portfolio=_portfolio(open_position_count=4)
    )
    assert _check(results, "max_concurrent_positions").passed is True


# --- 7. portfolio exposure ---------------------------------------------------


def test_exposure_within_limit_passes():
    results = _run(
        policy=_policy(max_portfolio_exposure_pct=Decimal("50.00")),
        portfolio=_portfolio(open_position_value=Decimal("10000")),
        position_value=Decimal("1000"),
    )
    assert _check(results, "portfolio_exposure").passed is True


def test_exposure_exceeding_limit_fails():
    results = _run(
        policy=_policy(max_portfolio_exposure_pct=Decimal("10.00")),
        portfolio=_portfolio(open_position_value=Decimal("9500")),
        position_value=Decimal("1000"),
    )
    assert _check(results, "portfolio_exposure").passed is False


def test_exposure_exactly_at_limit_passes():
    # 50% of 100000 = 50000 exactly.
    results = _run(
        policy=_policy(max_portfolio_exposure_pct=Decimal("50.00")),
        portfolio=_portfolio(open_position_value=Decimal("49000")),
        position_value=Decimal("1000"),
    )
    assert _check(results, "portfolio_exposure").passed is True


# --- 8. position size limit --------------------------------------------------


def test_position_size_within_limit_passes():
    results = _run(
        policy=_policy(max_position_size_pct=Decimal("5.00")),
        quantity=Decimal("10"),
        position_value=Decimal("1000"),
    )
    assert _check(results, "position_size_limit").passed is True


def test_position_size_exceeding_limit_fails():
    results = _run(
        policy=_policy(max_position_size_pct=Decimal("1.00")),
        quantity=Decimal("50"),
        position_value=Decimal("5000"),
    )
    assert _check(results, "position_size_limit").passed is False


def test_zero_quantity_fails_position_size_limit():
    results = _run(quantity=Decimal("0"), position_value=Decimal("0"))
    assert _check(results, "position_size_limit").passed is False


# --- 9/10. stop-loss / take-profit validity ----------------------------------


def test_valid_stop_and_target_pass():
    results = _run(
        entry_price=Decimal("100"),
        stop_loss_price=Decimal("98"),
        take_profit_price=Decimal("104"),
    )
    assert _check(results, "stop_loss_validity").passed is True
    assert _check(results, "take_profit_validity").passed is True


def test_stop_above_entry_fails_stop_loss_validity():
    results = _run(entry_price=Decimal("100"), stop_loss_price=Decimal("101"))
    assert _check(results, "stop_loss_validity").passed is False


def test_zero_stop_fails_stop_loss_validity():
    results = _run(entry_price=Decimal("100"), stop_loss_price=Decimal("0"))
    assert _check(results, "stop_loss_validity").passed is False


def test_negative_entry_fails_stop_loss_validity():
    results = _run(entry_price=Decimal("-5"), stop_loss_price=Decimal("-10"))
    assert _check(results, "stop_loss_validity").passed is False


def test_target_below_entry_fails_take_profit_validity():
    results = _run(entry_price=Decimal("100"), take_profit_price=Decimal("99"))
    assert _check(results, "take_profit_validity").passed is False


def test_zero_take_profit_fails_take_profit_validity():
    results = _run(entry_price=Decimal("100"), take_profit_price=Decimal("0"))
    assert _check(results, "take_profit_validity").passed is False


def test_missing_entry_price_fails_both_stop_and_target_validity():
    results = _run(entry_price=None, stop_loss_price=None, take_profit_price=None)
    assert _check(results, "stop_loss_validity").passed is False
    assert _check(results, "take_profit_validity").passed is False


# --- 11. loss cooldown --------------------------------------------------------


def test_no_prior_loss_passes_cooldown():
    results = _run(portfolio=_portfolio(last_losing_trade_at=None))
    assert _check(results, "loss_cooldown").passed is True


def test_recent_loss_inside_cooldown_fails():
    results = _run(
        policy=_policy(cooldown_after_loss_minutes=60),
        portfolio=_portfolio(last_losing_trade_at=NOW - timedelta(minutes=30)),
        now=NOW,
    )
    assert _check(results, "loss_cooldown").passed is False


def test_loss_exactly_at_cooldown_boundary_passes():
    results = _run(
        policy=_policy(cooldown_after_loss_minutes=60),
        portfolio=_portfolio(last_losing_trade_at=NOW - timedelta(minutes=60)),
        now=NOW,
    )
    assert _check(results, "loss_cooldown").passed is True


def test_loss_just_inside_cooldown_boundary_fails():
    results = _run(
        policy=_policy(cooldown_after_loss_minutes=60),
        portfolio=_portfolio(last_losing_trade_at=NOW - timedelta(minutes=59, seconds=59)),
        now=NOW,
    )
    assert _check(results, "loss_cooldown").passed is False


def test_loss_well_past_cooldown_passes():
    results = _run(
        policy=_policy(cooldown_after_loss_minutes=60),
        portfolio=_portfolio(last_losing_trade_at=NOW - timedelta(hours=5)),
        now=NOW,
    )
    assert _check(results, "loss_cooldown").passed is True


# --- rejections always continue and report the complete picture -------------


def test_multiple_independent_failures_are_all_reported():
    results = _run(
        policy=_policy(max_daily_loss_pct=Decimal("3.00"), max_drawdown_pct=Decimal("15.00")),
        portfolio=_portfolio(
            realized_pl_today=Decimal("-5000"),
            high_water_mark=Decimal("100000"),
            equity=Decimal("80000"),
        ),
    )
    assert _check(results, "daily_loss_limit").passed is False
    assert _check(results, "max_drawdown").passed is False
    # Neither failure caused the other to be skipped.
    assert _check(results, "daily_loss_limit").skipped is False
    assert _check(results, "max_drawdown").skipped is False


def _check(results, name: str):
    return next(c for c in results if c.name == name)
