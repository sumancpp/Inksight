from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_cors_preflight_options():
    """Verify OPTIONS preflight request returns 200 OK with proper CORS headers."""
    response = client.options(
        "/api/v1/answer-sheets/1/infer-questions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


def test_cors_preflight_options_127():
    """Verify OPTIONS preflight request for 127.0.0.1:5173 returns 200 OK with proper CORS headers."""
    response = client.options(
        "/api/v1/answer-sheets/1/infer-questions",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_success_response():
    """Verify successful response contains CORS headers for origin."""
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_401_unauthorized_error():
    """Verify 401 Unauthorized responses retain Access-Control-Allow-Origin header."""
    response = client.post(
        "/api/v1/answer-sheets/1/infer-questions",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_404_not_found_error():
    """Verify 404 Not Found responses retain Access-Control-Allow-Origin header."""
    response = client.get(
        "/api/v1/non-existent-route-for-testing",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 404
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_500_server_error():
    """Verify unhandled 500 server errors retain Access-Control-Allow-Origin header instead of masking as CORS failure."""
    # Temporarily register a route that triggers an unhandled exception
    @app.get("/api/v1/test-cors-internal-crash")
    async def crash():
        raise RuntimeError("Simulated crash for CORS verification")

    response = client.get(
        "/api/v1/test-cors-internal-crash",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.json()["error"]["code"] == 500

