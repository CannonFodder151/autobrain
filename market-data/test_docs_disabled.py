"""Regression test: /docs, /redoc, /openapi.json disabled in production (AUT-1745).

Mirrors backend + rego-lookup-api behavior — CWE-200 information disclosure prevention.
Run: ENVIRONMENT=production python test_docs_disabled.py
"""

import os
import sys

os.environ.setdefault("API_KEY", "test-key")

sys.path.insert(0, ".")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ENV = os.getenv("ENVIRONMENT", "production")
client = TestClient(main.app)


def test_docs_disabled_in_production():
    """In production, /docs + /openapi.json return 404. /redoc is always 404
    (we don't run redoc on this service; matches backend convention)."""
    if ENV == "production":
        assert client.get("/docs").status_code == 404, f"/docs must be disabled in production, got {client.get('/docs').status_code}"
        assert client.get("/openapi.json").status_code == 404, f"/openapi.json must be disabled in production, got {client.get('/openapi.json').status_code}"
    else:
        assert client.get("/docs").status_code == 200, f"/docs must be enabled in non-prod, got {client.get('/docs').status_code}"
        assert client.get("/openapi.json").status_code == 200, f"/openapi.json must be enabled in non-prod, got {client.get('/openapi.json').status_code}"
    # /redoc is unconditionally disabled — we don't ship redoc here.
    assert client.get("/redoc").status_code == 404, f"/redoc is always disabled, got {client.get('/redoc').status_code}"


def test_health_unaffected():
    assert client.get("/health").status_code == 200


def test_search_still_health():
    """Sanity: docs gating does not break /health."""
    r = client.get("/health")
    assert r.json().get("status") == "ok"


if __name__ == "__main__":
    test_docs_disabled_in_production()
    test_health_unaffected()
    test_search_still_health()
    print(f"ENVIRONMENT={ENV}: all docs-disabled checks passed")