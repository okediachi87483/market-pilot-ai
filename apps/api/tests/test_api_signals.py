"""API tests for /api/v1/signals. Require the live Postgres + seeded
fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine)."""

from fastapi.testclient import TestClient


def test_evaluate_returns_a_candidate_signal(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/signals/evaluate/AAPL", params={"interval": "1d"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["signal"] in ("BUY", "SELL", "HOLD")
    assert body["status"] == "CANDIDATE"
    assert body["strategy_id"] == "trend_momentum"
    assert body["strategy_version"] == "1.0.0"
    assert body["strategy_label"] == "trend_momentum_v1"
    assert isinstance(body["reasons"], list) and len(body["reasons"]) > 0
    assert "was_newly_created" in body


def test_evaluate_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/signals/evaluate/ZZZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_evaluate_invalid_interval_returns_422(client: TestClient, db_engine) -> None:
    resp = client.post("/api/v1/signals/evaluate/AAPL", params={"interval": "3d"})
    assert resp.status_code == 422


def test_repeated_evaluate_calls_are_deduplicated(client: TestClient, db_engine) -> None:
    first = client.post("/api/v1/signals/evaluate/MSFT", params={"interval": "1d"}).json()
    second = client.post("/api/v1/signals/evaluate/MSFT", params={"interval": "1d"}).json()
    assert first["id"] == second["id"]
    assert second["was_newly_created"] is False


def test_list_signals_returns_evaluated_signals(client: TestClient, db_engine) -> None:
    client.post("/api/v1/signals/evaluate/NVDA", params={"interval": "1d"})
    resp = client.get("/api/v1/signals", params={"symbol": "NVDA"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert all(item["symbol"] == "NVDA" for item in body)


def test_list_signals_filters_by_status(client: TestClient, db_engine) -> None:
    client.post("/api/v1/signals/evaluate/TSLA", params={"interval": "1d"})
    resp = client.get("/api/v1/signals", params={"symbol": "TSLA", "status": "CANDIDATE"})
    assert resp.status_code == 200
    assert all(item["status"] == "CANDIDATE" for item in resp.json())


def test_get_signal_by_id(client: TestClient, db_engine) -> None:
    evaluated = client.post("/api/v1/signals/evaluate/AMZN", params={"interval": "1d"}).json()
    resp = client.get(f"/api/v1/signals/{evaluated['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == evaluated["id"]


def test_get_signal_unknown_id_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/signals/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_signal_malformed_id_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/signals/not-a-uuid")
    assert resp.status_code == 422


def test_signal_response_never_contains_a_probability_percentage(
    client: TestClient, db_engine
) -> None:
    body = client.post("/api/v1/signals/evaluate/AAPL", params={"interval": "1d"}).json()
    serialized = " ".join(body["reasons"])
    assert "%" not in serialized
    assert "chance of" not in serialized.lower()
