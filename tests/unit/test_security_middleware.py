"""Security middleware tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_security_headers_present() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Correlation-ID"]


def test_body_size_limit() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/health-score", content=b"x" * 20000)
    assert response.status_code == 413
    assert response.headers["X-Correlation-ID"]


def test_rate_limit_header() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Limit" in response.headers


def test_correlation_id_propagated() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"X-Correlation-ID": "abc123"})
    assert response.headers["X-Correlation-ID"] == "abc123"


def test_401_generic_message() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/admin/test", json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."
    assert response.headers["X-Correlation-ID"]


if __name__ == "__main__":
    test_security_headers_present()
    test_body_size_limit()
    test_rate_limit_header()
    test_correlation_id_propagated()
    test_401_generic_message()
    print("all security tests passed")
