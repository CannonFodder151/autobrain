"""AUT-302: AI gateway rate limiting (defense in depth).

Regression: N+1 authenticated inference calls within a window must yield 429
on call N+1. Uses a tiny per-window cap so the test runs in-memory.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import _rate_windows, app

client = TestClient(app)

BOGUS_ROUTER = "http://your-9router-instance:port/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AI_ROUTER_URL", BOGUS_ROUTER)
    monkeypatch.setenv("AI_ENV", "development")  # auth off for the test
    monkeypatch.setenv("AI_GATEWAY_RATE_LIMIT_PER_WINDOW", "2")
    monkeypatch.setenv("AI_GATEWAY_GLOBAL_RATE_LIMIT_PER_WINDOW", "1000")
    monkeypatch.setenv("AI_GATEWAY_RATE_WINDOW_SECONDS", "60")
    _rate_windows.clear()
    yield
    _rate_windows.clear()


def test_n_plus_one_returns_429() -> None:
    payload = {"payload": {"symptoms": "squealing brakes"}}
    assert client.post("/v1/diagnostics", json=payload).status_code == 200
    assert client.post("/v1/diagnostics", json=payload).status_code == 200
    assert client.post("/v1/diagnostics", json=payload).status_code == 429


def test_global_limit_also_429(monkeypatch) -> None:
    monkeypatch.setenv("AI_GATEWAY_RATE_LIMIT_PER_WINDOW", "1000")
    monkeypatch.setenv("AI_GATEWAY_GLOBAL_RATE_LIMIT_PER_WINDOW", "1")
    _rate_windows.clear()
    payload = {"payload": {"symptoms": "squealing brakes"}}
    assert client.post("/v1/diagnostics", json=payload).status_code == 200
    assert client.post("/v1/diagnostics", json=payload).status_code == 429
