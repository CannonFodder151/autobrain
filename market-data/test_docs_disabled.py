"""Regression test: /docs and /openapi.json are disabled in production (AUT-1745).

Mirrors the backend's behavior — CWE-200 information disclosure prevention.
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


def test_docs_disabled_when_production():
    """By default (no ENVIRONMENT set) docs must be disabled (prod-safe)."""
    r = client.get("/docs")
    if ENV == "production":
        assert r.status_code == 404, f"production must disable /docs, got {r.status_code}"
    else:
        assert r.status_code == 200, f"non-prod must expose /docs, got {r.status_code}"
    r = client.get("/openapi.json")
    if ENV == "production":
        assert r.status_code == 404, f"production must disable /openapi.json, got {r.status_code}"
    else:
        assert r.status_code == 200, f"non-prod must expose /openapi.json, got {r.status_code}"
    r = client.get("/redoc")
    assert r.status_code == 404, f"redoc must always be disabled (autobrain backend pattern), got {r.status_code}"


if __name__ == "__main__":
    test_docs_disabled_when_production()
    print(f"ENVIRONMENT={ENV}: all docs-disabled checks passed")
