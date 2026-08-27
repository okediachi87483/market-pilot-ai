"""API tests for /api/v1/paper. Require the live Postgres + seeded
fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine).

Signals are inserted directly via `db_session` (status `RISK_APPROVED`,
with a backing `RiskEvaluation`) so each test controls the exact
approved quantity, the same pattern test_paper_service.py uses."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.asset import Asset
from app.models.risk import RiskEvaluation, RiskPolicy
from app.models.signal import Signal


async def _make_risk_approved_signal(db_session, symbol: str, quantity: Decimal, signal_type="BUY"):
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one()
    policy_result = await db_session.execute(
        select(RiskPolicy).where(RiskPolicy.is_active.is_(True))
    )
    policy = policy_result.scalar_one()

    signal = Signal(
        asset_id=asset.id,
        interval="1d",
        signal=signal_type,
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG" if signal_type == "BUY" else None,
        market_regime="BULLISH",
        reasons=["test fixture signal"],
        supporting_features={},
        invalidating_conditions=[],
        status="RISK_APPROVED",
        generated_at=datetime.now(UTC),
    )
    db_session.add(signal)
    await db_session.flush()

    evaluation = RiskEvaluation(
        signal_id=signal.id,
        policy_id=policy.id,
        policy_version=policy.version,
        decision="APPROVED",
        reasons=[],
        checks=[],
        calculated_position_size=quantity,
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("98.00"),
        take_profit_price=Decimal("104.00"),
        position_value=quantity * Decimal("100.00"),
        portfolio_snapshot={},
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


async def _make_candidate_signal(db_session, symbol: str):
    asset_result = await db_session.execute(select(Asset).where(Asset.symbol == symbol))
    asset = asset_result.scalar_one()
    signal = Signal(
        asset_id=asset.id,
        interval="1d",
        signal="BUY",
        strategy_id="trend_momentum",
        strategy_version="1.0.0",
        strength="STRONG",
        market_regime="BULLISH",
        reasons=["test fixture signal"],
        supporting_features={},
        invalidating_conditions=[],
        status="CANDIDATE",
        generated_at=datetime.now(UTC),
    )
    db_session.add(signal)
    await db_session.commit()
    await db_session.refresh(signal)
    return signal


def test_get_paper_portfolio(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/portfolio")
    assert resp.status_code == 200
    body = resp.json()
    for field in (
        "starting_equity",
        "cash",
        "market_value",
        "equity",
        "realized_pnl_total",
        "unrealized_pnl",
        "total_pnl",
        "daily_pnl",
        "peak_equity",
        "drawdown_pct",
        "open_position_count",
    ):
        assert field in body


def test_list_paper_positions(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/positions", params={"status": "OPEN"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_paper_orders(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/orders")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_paper_order_unknown_id_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/orders/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_paper_order_malformed_id_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/orders/not-a-uuid")
    assert resp.status_code == 422


def test_list_paper_fills(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/paper/fills")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_execute_paper_order_for_a_risk_approved_signal(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_risk_approved_signal(db_session, "AAPL", Decimal("1"))

    resp = client.post(f"/api/v1/paper/execute/{signal.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["signal_id"] == str(signal.id)
    assert body["symbol"] == "AAPL"
    assert body["side"] == "BUY"
    assert body["status"] in ("FILLED", "REJECTED")


@pytest.mark.asyncio
async def test_execute_paper_order_twice_returns_409(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_risk_approved_signal(db_session, "MSFT", Decimal("1"))

    first = client.post(f"/api/v1/paper/execute/{signal.id}")
    second = client.post(f"/api/v1/paper/execute/{signal.id}")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


@pytest.mark.asyncio
async def test_execute_paper_order_for_a_candidate_signal_returns_409(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_candidate_signal(db_session, "NVDA")

    resp = client.post(f"/api/v1/paper/execute/{signal.id}")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_execute_paper_order_unknown_signal_returns_404(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/paper/execute/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_execute_paper_order_malformed_signal_id_returns_422(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/paper/execute/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_close_paper_position(client: TestClient, db_session, db_engine) -> None:
    signal = await _make_risk_approved_signal(db_session, "AMZN", Decimal("1"))
    client.post(f"/api/v1/paper/execute/{signal.id}")

    resp = client.post("/api/v1/paper/positions/AMZN/close")

    assert resp.status_code == 200
    body = resp.json()
    assert body["side"] == "SELL"
    assert body["status"] == "FILLED"


def test_close_paper_position_with_no_open_position_returns_404(
    client: TestClient, db_engine
) -> None:
    resp = client.post("/api/v1/paper/positions/NOSUCHSYMBOL/close")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_paper_order_response_never_uses_certainty_language(
    client: TestClient, db_session, db_engine
) -> None:
    signal = await _make_risk_approved_signal(db_session, "TSLA", Decimal("1"))
    resp = client.post(f"/api/v1/paper/execute/{signal.id}")
    body = resp.json()
    serialized = str(body).lower()
    for banned in ("guaranteed", "real trade", "real order", "real broker"):
        assert banned not in serialized
