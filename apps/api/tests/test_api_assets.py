"""API tests for /api/v1/assets. Require the live Postgres + the seeded
fixture assets from the Alembic migration — auto-skipped if Postgres is
unreachable (see tests/conftest.py db_engine)."""

from fastapi.testclient import TestClient


def test_list_assets_returns_seeded_fixtures(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets")
    assert resp.status_code == 200
    symbols = {a["symbol"] for a in resp.json()}
    assert {"AAPL", "MSFT", "NVDA", "AMZN", "TSLA"}.issubset(symbols)


def test_list_assets_response_shape(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets")
    asset = resp.json()[0]
    assert set(asset.keys()) == {
        "id",
        "symbol",
        "name",
        "asset_type",
        "exchange",
        "currency",
        "active",
        "created_at",
        "updated_at",
    }


def test_list_assets_filters_by_asset_type(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets", params={"asset_type": "equity"})
    assert resp.status_code == 200
    assert all(a["asset_type"] == "equity" for a in resp.json())

    resp = client.get("/api/v1/assets", params={"asset_type": "crypto"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_asset_by_symbol(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["name"] == "Apple Inc."


def test_get_asset_is_case_insensitive(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets/aapl")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "AAPL"


def test_get_unknown_asset_returns_404_envelope(client: TestClient, db_engine) -> None:
    resp = client.get("/api/v1/assets/ZZZZ")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
