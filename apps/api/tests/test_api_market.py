"""API tests for /api/v1/market. Require the live Postgres + seeded
fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine)."""

from fastapi.testclient import TestClient


def test_get_quote_returns_mock_labeled_bar(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["source"] == "mock"
    assert body["is_mock"] is True
    bar = body["bar"]
    assert set(bar.keys()) == {"timestamp", "open", "high", "low", "close", "volume"}
    assert float(bar["open"]) > 0


def test_get_quote_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/ZZZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_history_default_range(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/MSFT/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "1d"
    assert body["is_mock"] is True
    assert body["count"] == len(body["bars"])
    assert body["count"] > 0


def test_get_history_explicit_range(client: TestClient, db_engine) -> None:
    resp = client.get(
        "/api/v1/market/NVDA/history",
        params={"interval": "1h", "start": "2024-06-01T00:00:00Z", "end": "2024-06-01T05:00:00Z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 6
    timestamps = [bar["timestamp"] for bar in body["bars"]]
    assert timestamps == sorted(timestamps)


def test_get_history_invalid_interval_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/AAPL/history", params={"interval": "3d"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["interval"] == "3d"


def test_get_history_start_after_end_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get(
        "/api/v1/market/AAPL/history",
        params={"start": "2024-06-05T00:00:00Z", "end": "2024-06-01T00:00:00Z"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_get_history_malformed_date_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/AAPL/history", params={"start": "not-a-date"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_get_history_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/market/ZZZZ/history")
    assert resp.status_code == 404


def test_repeated_history_requests_are_idempotent_at_api_level(
    client: TestClient, db_engine
) -> None:
    params = {"interval": "1h", "start": "2024-07-01T00:00:00Z", "end": "2024-07-01T03:00:00Z"}
    first = client.get("/api/v1/market/TSLA/history", params=params).json()
    second = client.get("/api/v1/market/TSLA/history", params=params).json()
    assert first["bars"] == second["bars"]
    assert first["count"] == 4
