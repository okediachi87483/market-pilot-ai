"""API tests for /api/v1/risk. Require the live Postgres + seeded
fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine).

Signals used here are inserted directly via `db_session` (not through
`POST /signals/evaluate`) so each test controls the exact signal type
(BUY/SELL/HOLD) it evaluates, independent of whatever the deterministic
mock market data happens to produce for "today" (see
tests/test_risk_service.py's module docstring for the same pattern).
Only invalid `PUT /risk/rules` payloads are exercised here, with one
exception: `test_evaluate_risk_approves_a_healthy_buy_signal` issues a
valid PUT to temporarily zero `cooldown_after_loss_minutes`, because
since Phase 7 the active policy evaluates against *real* paper-trading
state — a real loss realized by some other test (fees exceeding a tiny
gain on a close, say) can put the shared account into a genuine
loss-cooldown that would otherwise reject even this well-formed
candidate. That one test captures the original policy via `GET
/risk/rules` and restores it in a `finally` block, the same
capture-and-restore discipline test_risk_service.py's
`test_update_policy_...` established.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.asset import Asset
from app.models.signal import Signal

_POLICY_FIELDS = (
    "enabled",
    "max_position_size_pct",
    "max_portfolio_exposure_pct",
    "max_daily_loss_pct",
    "max_drawdown_pct",
    "stop_loss_pct",
    "take_profit_pct",
    "risk_per_trade_pct",
    "max_concurrent_positions",
    "cooldown_after_loss_minutes",
)


async def _make_signal(db_session, symbol: str, signal_type: str) -> Signal:
    result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalar_one()
    row = Signal(
        asset_id=asset.id,
        interval="1d",
        signal=signal_type,
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG" if signal_type in ("BUY", "SELL") else None,
        market_regime="BULLISH" if signal_type == "BUY" else "BEARISH",
        reasons=["test fixture signal"],
        supporting_features={"rsi14": 55.0},
        invalidating_conditions=[],
        status="CANDIDATE",
        generated_at=datetime.now(UTC),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


def test_get_risk_summary(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert "portfolio" in body and "policy" in body
    assert body["portfolio"]["equity"]
    assert body["policy"]["enabled"] is True


def test_get_risk_rules_returns_active_policy(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/risk/rules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is True
    assert float(body["max_position_size_pct"]) > 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_position_size_pct", "-1"),
        ("max_position_size_pct", "0"),
        ("max_position_size_pct", "150"),
        ("max_portfolio_exposure_pct", "0"),
        ("max_daily_loss_pct", "-5"),
        ("max_drawdown_pct", "0"),
        ("stop_loss_pct", "0"),
        ("stop_loss_pct", "100"),
        ("take_profit_pct", "0"),
        ("risk_per_trade_pct", "-1"),
        ("max_concurrent_positions", "0"),
        ("cooldown_after_loss_minutes", "-1"),
    ],
)
def test_put_risk_rules_rejects_unsafe_values(
    client: TestClient, db_engine, field: str, value: str
) -> None:
    valid_payload = {
        "enabled": True,
        "max_position_size_pct": "5.00",
        "max_portfolio_exposure_pct": "50.00",
        "max_daily_loss_pct": "3.00",
        "max_drawdown_pct": "15.00",
        "stop_loss_pct": "2.00",
        "take_profit_pct": "4.00",
        "risk_per_trade_pct": "1.00",
        "max_concurrent_positions": 5,
        "cooldown_after_loss_minutes": 60,
    }
    valid_payload[field] = value
    resp = client.put("/api/v1/risk/rules", json=valid_payload)
    assert resp.status_code == 422


def test_put_risk_rules_rejects_missing_field(client: TestClient, db_engine) -> None:
    resp = client.put("/api/v1/risk/rules", json={"enabled": True})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_evaluate_risk_approves_a_healthy_buy_signal(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY")

    original = {k: client.get("/api/v1/risk/rules").json()[k] for k in _POLICY_FIELDS}
    neutralized = dict(original)
    neutralized["cooldown_after_loss_minutes"] = 0
    # Phase 9.5: also neutralize drawdown/daily-loss — a long-lived local
    # database accumulates a genuine drawdown across repeated suite runs
    # (see test_risk_service.py's _neutralize_cooldown for the full note).
    neutralized["max_drawdown_pct"] = "99"
    neutralized["max_daily_loss_pct"] = "99"
    assert client.put("/api/v1/risk/rules", json=neutralized).status_code == 200

    try:
        resp = client.post(f"/api/v1/risk/evaluate/{signal.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "APPROVED"
        assert body["symbol"] == "AAPL"
        assert len(body["checks"]) == 11
        assert body["calculated_position_size"] is not None
        assert float(body["calculated_position_size"]) > 0
        assert body["stop_loss_price"] is not None
        assert body["take_profit_price"] is not None
    finally:
        assert client.put("/api/v1/risk/rules", json=original).status_code == 200


@pytest.mark.asyncio
async def test_evaluate_risk_rejects_a_sell_signal_with_reasons(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "MSFT", "SELL")

    resp = client.post(f"/api/v1/risk/evaluate/{signal.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "REJECTED"
    assert len(body["reasons"]) >= 1


def test_evaluate_risk_unknown_signal_returns_404(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/risk/evaluate/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_evaluate_risk_malformed_signal_id_returns_422(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/risk/evaluate/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_evaluate_risk_twice_returns_409_on_second_call(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "NVDA", "BUY")

    first = client.post(f"/api/v1/risk/evaluate/{signal.id}")
    second = client.post(f"/api/v1/risk/evaluate/{signal.id}")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


@pytest.mark.asyncio
async def test_list_risk_evaluations_filters_by_decision(
    client: TestClient, db_session, db_engine
) -> None:
    approved_signal = await _make_signal(db_session, "AMZN", "BUY")
    rejected_signal = await _make_signal(db_session, "TSLA", "SELL")
    client.post(f"/api/v1/risk/evaluate/{approved_signal.id}")
    client.post(f"/api/v1/risk/evaluate/{rejected_signal.id}")

    resp = client.get("/api/v1/risk/evaluations", params={"decision": "APPROVED"})
    assert resp.status_code == 200
    assert all(item["decision"] == "APPROVED" for item in resp.json())


@pytest.mark.asyncio
async def test_get_risk_evaluation_by_id(client: TestClient, db_session, db_engine) -> None:
    signal = await _make_signal(db_session, "AAPL", "BUY")
    evaluated = client.post(f"/api/v1/risk/evaluate/{signal.id}").json()

    resp = client.get(f"/api/v1/risk/evaluations/{evaluated['id']}")

    assert resp.status_code == 200
    assert resp.json()["id"] == evaluated["id"]


def test_get_risk_evaluation_unknown_id_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/risk/evaluations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_risk_response_never_uses_certainty_language(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_signal(db_session, "MSFT", "BUY")
    body = client.post(f"/api/v1/risk/evaluate/{signal.id}").json()

    serialized = " ".join(body["reasons"] + [c["detail"] for c in body["checks"]]).lower()
    for banned in ("guaranteed", "winning trade", "safe trade", "certain profit"):
        assert banned not in serialized
