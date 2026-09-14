"""Regression tests for fail-closed gateway auth (AUT-199, AUT-3076).

Before: require_gateway_key returned early (open gateway, 200) whenever
AI_GATEWAY_AUTH_DISABLED=1 was set. After: that env var is ignored; the only
development bypass is ENVIRONMENT=development.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BOGUS_ROUTER = "http://your-9router-instance:port/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AI_ROUTER_URL", BOGUS_ROUTER)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("AI_GATEWAY_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AI_ENV", raising=False)


def test_no_key_fails_closed():
    # Repro from the finding: gateway without AI_GATEWAY_API_KEY must NOT 200.
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_missing_token_rejected(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "correct-secret")
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "correct-secret")
    resp = client.post(
        "/v1/diagnostics",
        json={"payload": {"symptoms": "squealing brakes"}},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401


def test_correct_token_accepted(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "correct-secret")
    resp = client.post(
        "/v1/diagnostics",
        json={"payload": {"symptoms": "squealing brakes"}},
        headers={"Authorization": "Bearer correct-secret"},
    )
    assert resp.status_code == 200


def test_modules_endpoint_requires_auth():
    assert client.get("/v1/modules").status_code == 401


def test_auth_disabled_flag_no_longer_bypasses(monkeypatch):
    """AUT-3076: AI_GATEWAY_AUTH_DISABLED=1 must NOT open the gateway."""
    monkeypatch.setenv("AI_GATEWAY_AUTH_DISABLED", "1")
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_environment_development_bypasses_auth(monkeypatch):
    """ENVIRONMENT=development is the only allowed dev bypass."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 200


def test_ai_env_development_does_not_bypass(monkeypatch):
    """AI_ENV=development is not an auth opt-out."""
    monkeypatch.setenv("AI_ENV", "development")
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_health_stays_open():
    assert client.get("/health").status_code == 200
