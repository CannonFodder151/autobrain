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
    monkeypatch.setenv("AI_GATEWAY_AUTH_DISABLED", "1")  # auth off for the test
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


def test_overflow_evicts_stale_not_all(monkeypatch) -> None:
    """AUT-1605: overflow must evict stale entries, not clear all state.

    Attack: 10K+ distinct IPs fill the dict, then overflow triggers.
    Before fix: _rate_windows.clear() resets ALL clients' quotas.
    After fix: only stale (old-bucket) entries are evicted; current-bucket
    entries and the 'global' key survive with their counters intact.
    """
    import time

    from app.main import _window_allows

    bucket = int(time.time()) // 60

    _rate_windows.clear()
    # Fill with 10_001 stale entries (old bucket)
    for i in range(10_001):
        _rate_windows[f"stale:{i}"] = (bucket - 1, 1)

    # Insert a legitimate current-bucket entry at count=1, limit=2
    legit_key = "ip:10.0.0.1"
    _rate_windows[legit_key] = (bucket, 1)
    _rate_windows["global"] = (bucket, 1)

    # First call: should pass (count goes 1→2)
    assert _window_allows(legit_key, 2, 60) is True
    # Second call: should be blocked (count=2, limit=2)
    assert _window_allows(legit_key, 2, 60) is False

    # Stale entries should have been evicted, but legit key must survive
    assert legit_key in _rate_windows, "current-bucket entry lost after overflow"
    assert "global" in _rate_windows, "global counter lost after overflow"
    # Stale keys should be gone (at least half evicted)
    stale_remaining = sum(1 for k in _rate_windows if k.startswith("stale:"))
    assert stale_remaining < 10_001, "stale entries not evicted"
