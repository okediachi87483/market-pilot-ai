"""API tests for /api/v1/analysis. Require the live Postgres + seeded
fixture assets — auto-skipped if Postgres is unreachable (see
tests/conftest.py db_engine)."""

from fastapi.testclient import TestClient


def test_get_analysis_returns_full_snapshot(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/AAPL", params={"interval": "1d"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["is_mock"] is True
    assert set(body["indicators"].keys()) == {"trend", "momentum", "volatility", "volume"}
    assert set(body["indicators"]["trend"].keys()) == {
        "sma20",
        "sma50",
        "sma200",
        "ema9",
        "ema21",
        "ema50",
        "ema200",
    }
    assert body["regime"]["regime"] in {
        "BULLISH",
        "BEARISH",
        "SIDEWAYS",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "INSUFFICIENT_DATA",
    }
    assert isinstance(body["regime"]["reasons"], list) and body["regime"]["reasons"]


def test_get_analysis_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/ZZZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_analysis_invalid_interval_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/AAPL", params={"interval": "3d"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_get_indicator_series_returns_points(client: TestClient, db_engine) -> None:
    resp = client.get(
        "/api/v1/analysis/MSFT/indicators",
        params={"interval": "1h", "start": "2024-06-01T00:00:00Z", "end": "2024-06-01T05:00:00Z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 6
    assert len(body["points"]) == 6
    for point in body["points"]:
        assert "close" in point and "sma20" in point and "rsi14" in point


def test_get_indicator_series_start_after_end_returns_422(client: TestClient, db_engine) -> None:
    resp = client.get(
        "/api/v1/analysis/AAPL/indicators",
        params={"start": "2024-06-05T00:00:00Z", "end": "2024-06-01T00:00:00Z"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_get_indicator_series_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/ZZZZ/indicators")
    assert resp.status_code == 404


def test_get_regime_endpoint(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/NVDA/regime", params={"interval": "1d"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NVDA"
    assert "regime" in body
    assert "reasons" in body
    assert "candle_count" in body


def test_get_regime_unknown_symbol_returns_404(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/analysis/ZZZZ/regime")
    assert resp.status_code == 404


def test_repeated_analysis_requests_are_deterministic(client: TestClient, db_engine) -> None:
    params = {"interval": "1h", "start": "2024-06-01T00:00:00Z", "end": "2024-06-01T10:00:00Z"}
    first = client.get("/api/v1/analysis/TSLA/indicators", params=params).json()
    second = client.get("/api/v1/analysis/TSLA/indicators", params=params).json()
    assert first["points"] == second["points"]
