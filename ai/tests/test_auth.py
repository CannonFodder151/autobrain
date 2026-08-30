"""Regression tests for fail-closed gateway auth (AUT-199).

Before: require_gateway_key returned early (open gateway, 200) whenever
AI_GATEWAY_API_KEY was unset. After: /v1/* rejects with 401 unless an explicit
development opt-out (AI_ENV=development or AI_GATEWAY_AUTH_DISABLED=1) is set.
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


@pytest.mark.parametrize("optout", [("AI_GATEWAY_AUTH_DISABLED", "1")])
def test_dev_optout_opens_gateway(monkeypatch, optout):
    monkeypatch.setenv(optout[0], optout[1])
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 200


def test_ai_env_development_no_longer_bypasses_auth(monkeypatch):
    """AUT-1185 FINDING-05: AI_ENV=development is not an auth opt-out."""
    monkeypatch.setenv("AI_ENV", "development")
    monkeypatch.delenv("AI_GATEWAY_AUTH_DISABLED", raising=False)
    resp = client.post("/v1/diagnostics", json={"payload": {"symptoms": "squealing brakes"}})
    assert resp.status_code == 401


def test_health_stays_open():
    assert client.get("/health").status_code == 200
