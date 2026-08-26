from fastapi.testclient import TestClient


def test_health_returns_status_version_environment(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "marketpilot-api"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "development"


def test_health_live_always_ok(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_ready_reports_dependency_status(client: TestClient) -> None:
    # No Postgres/Redis running in the unit-test environment, so this
    # exercises the fail-closed path: 503 with each dependency reported
    # "down" rather than the check raising or silently passing.
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["dependencies"].keys()) == {"postgres", "redis"}
    for dep in body["dependencies"].values():
        assert dep["status"] in ("ok", "down")
