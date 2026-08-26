from fastapi.testclient import TestClient


def test_v1_namespace_is_mounted(client: TestClient) -> None:
    resp = client.get("/api/v1/")
    assert resp.status_code == 200
    assert resp.json()["namespace"] == "v1"
