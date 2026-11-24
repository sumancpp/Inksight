from fastapi.testclient import TestClient


def test_root_health(client: TestClient):
    """Test the root /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
    assert "x-process-time" in response.headers


def test_api_v1_health(client: TestClient):
    """Test the /api/v1/health endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "LearnGraph"
    assert data["version"] == "0.1.0"
    assert data["api_version"] == "v1"
    assert "environment" in data


def test_not_found_error_handler(client: TestClient):
    """Test custom error handling for non-existent routes."""
    response = client.get("/api/v1/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == 404
    assert "message" in data["error"]
    assert data["error"]["path"] == "/api/v1/non-existent-route"
