"""API tests for GET /api/v1/command-center. Require the live Postgres +
seeded fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine).

This endpoint is a read-only aggregation — no test here evaluates a
signal, runs a risk check, or executes a paper order; it only asserts
on the *shape* and *composition* of already-existing state, since the
underlying values are exercised by each owning phase's own test suite
(test_api_signals.py, test_api_risk.py, test_api_paper.py, test_api_ai.py).
"""

from fastapi.testclient import TestClient


def test_command_center_returns_full_snapshot(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL"})

    assert resp.status_code == 200
    body = resp.json()

    assert body["market"]["symbol"] == "AAPL"
    assert "generated_at" in body
    assert set(body["system_health"].keys()) == {"api", "database", "redis", "market_data", "ai"}
    assert body["system_health"]["api"] == "ok"
    assert body["system_health"]["database"] == "ok"
    assert body["system_health"]["redis"] == "ok"
    assert isinstance(body["watchlist"], list) and len(body["watchlist"]) > 0
    assert isinstance(body["signals"], list)
    assert isinstance(body["ai_analyses"], list)
    assert "portfolio" in body["risk"] and "policy" in body["risk"]
    assert body["portfolio"]["equity"]
    assert isinstance(body["positions"], list)
    assert isinstance(body["recent_fills"], list)
    assert isinstance(body["recent_activity"], list)


def test_command_center_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "ZZZZ"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_command_center_unsupported_interval_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL", "interval": "3d"})
    assert resp.status_code == 422


def test_command_center_skips_unknown_watchlist_symbols_without_failing(
    client: TestClient, db_engine
) -> None:
    resp = client.get(
        "/api/v1/command-center",
        params={"symbol": "AAPL", "watchlist": "AAPL,ZZZZ,MSFT"},
    )

    assert resp.status_code == 200
    body = resp.json()
    symbols = [row["symbol"] for row in body["watchlist"]]
    assert symbols == ["AAPL", "MSFT"]  # the unknown symbol is silently skipped
    # at least one watchlist quote succeeded, so market data health is "ok"
    assert body["system_health"]["market_data"] == "ok"


def test_command_center_recent_activity_is_sorted_most_recent_first(
    client: TestClient, db_engine
) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL", "activity_limit": 20})
    assert resp.status_code == 200
    timestamps = [row["timestamp"] for row in resp.json()["recent_activity"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_command_center_activity_limit_is_respected(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL", "activity_limit": 3})
    assert resp.status_code == 200
    assert len(resp.json()["recent_activity"]) <= 3


def test_command_center_activity_events_use_only_known_types(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL", "activity_limit": 30})
    assert resp.status_code == 200
    known = {
        "SIGNAL_GENERATED",
        "RISK_APPROVED",
        "RISK_REJECTED",
        "AI_ANALYSIS_COMPLETED",
        "PAPER_ORDER_FILLED",
        "POSITION_CLOSED",
    }
    for row in resp.json()["recent_activity"]:
        assert row["type"] in known


def test_command_center_never_exposes_a_key_field(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center", params={"symbol": "AAPL"})
    body = resp.json()
    serialized_keys = {k.lower() for k in body["system_health"]["ai"]}
    assert not any("key" in k or "secret" in k or "token" in k for k in serialized_keys)
    # the AI section within system_health is exactly the same shape as
    # GET /ai/status — configured/available/provider/model, never a key
    assert set(body["system_health"]["ai"].keys()) == {
        "configured",
        "available",
        "provider",
        "model",
    }


def test_command_center_defaults_to_a_reasonable_watchlist(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/command-center")
    assert resp.status_code == 200
    body = resp.json()
    assert body["market"]["symbol"] == "AAPL"  # default selected symbol
    assert len(body["watchlist"]) > 0
