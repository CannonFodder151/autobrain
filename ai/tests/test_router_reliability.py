"""Tests for the AI router reliability layer (AUT-1968).

Covers:
  * Per-call timeout tightening (25s default; AI_ROUTER_TIMEOUT_SECONDS
    override).
  * Circuit breaker: consecutive failures open the breaker, cooldown elapses,
    success closes it. Half-open probe behavior.
  * enhance() short-circuit: when the deterministic baseline already covers
    every "AI-addable" schema field, the router is skipped entirely.
"""

import os

# Disable routing so the test never calls a live router.
os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.router_client import (  # noqa: E402
    _SCHEMAS,
    _ai_can_contribute,
    _breaker_open,
    enhance,
    reset_circuit_breaker,
)


@pytest.fixture(autouse=True)
def _reset_breaker():
    """Each test starts with a closed breaker."""
    reset_circuit_breaker()
    yield
    reset_circuit_breaker()


# ---------------------------------------------------------------------------
# Short-circuit
# ---------------------------------------------------------------------------


def test_short_circuit_skips_when_baseline_complete() -> None:
    """Diagnostics baseline has every schema field filled → AI cannot contribute."""
    schema = _SCHEMAS["diagnostics"]
    baseline = {
        "summary": "Misfire detected",
        "severity": "high",
        "estimated_cost": 250.0,
        "cost_range": [200, 350],
        "items": [{"cause": "misfire"}],
        "parts_needed": ["spark plugs"],
        "recommended_actions": ["Book inspection"],
    }
    assert _ai_can_contribute("diagnostics", baseline, schema) is False


def test_short_circuit_runs_when_baseline_missing_fields() -> None:
    """Resale baseline is empty → AI is needed for rrp/used_price."""
    assert _ai_can_contribute("resale", {}, _SCHEMAS["resale"]) is True


def test_short_circuit_runs_when_field_is_none() -> None:
    """A None schema field is considered missing — the AI can still add it."""
    schema = _SCHEMAS["diagnostics"]
    baseline = {
        "summary": "ok", "severity": "high", "estimated_cost": 100.0,
        "cost_range": [80, 140], "items": [], "parts_needed": ["x"],
        "recommended_actions": ["y"],
    }
    baseline["estimated_cost"] = None
    assert _ai_can_contribute("diagnostics", baseline, schema) is True


def test_short_circuit_bypassed_for_parts_guide() -> None:
    """parts-guide does per-item tidy; the baseline is the inventory, not the
    refined strings, so the short-circuit must not skip the router call."""
    schema = _SCHEMAS["parts-guide"]
    baseline = {
        "parts": [{"name": "x", "category": "y", "brand": "z",
                   "description": "d"}],
        "vehicle": {},
        "model": "rule-based",
    }
    assert _ai_can_contribute("parts-guide", baseline, schema) is True


def test_short_circuit_treats_empty_string_as_missing() -> None:
    schema = _SCHEMAS["condition"]
    baseline = {"summary": "   "}
    assert _ai_can_contribute("condition", baseline, schema) is True


def test_short_circuit_unknown_module_falls_through() -> None:
    """No schema → don't short-circuit; the caller has the right to make the
    call (and the merge will drop anything not whitelisted anyway)."""
    assert _ai_can_contribute("unknown-module", {"x": 1}, {}) is True


@pytest.mark.asyncio
async def test_enhance_skips_router_when_baseline_complete() -> None:
    """A complete diagnostics baseline must skip the router entirely."""
    baseline = {
        "summary": "Misfire", "severity": "high", "estimated_cost": 250.0,
        "cost_range": [200, 350], "items": [{"cause": "misfire"}],
        "parts_needed": ["spark plugs"], "recommended_actions": ["Book"],
        "model": "rule-based-fallback",
    }
    route_mock = AsyncMock(return_value={"summary": "AI overrode"})
    with patch("app.router_client.route", new=route_mock):
        out = await enhance("diagnostics", {"symptoms": "misfire"}, baseline)
    assert out == baseline  # router was never called
    route_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_enhance_calls_router_when_baseline_incomplete() -> None:
    """An incomplete baseline (e.g. condition needs `summary`) must hit the router."""
    baseline = {
        "condition": "good", "score": 80.0, "confidence": 0.9,
        "factors": {}, "model": "rule-based-fallback",
    }
    with patch("app.router_client.route",
               new=AsyncMock(return_value={"summary": "well-maintained"})):
        out = await enhance("condition", {}, baseline)
    assert out["summary"] == "well-maintained"
    assert out["model"] == "rule-based+ai"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold_failures(monkeypatch) -> None:
    """After 3 consecutive failures the breaker opens; subsequent calls skip."""
    monkeypatch.setenv("AI_ROUTER_BREAKER_THRESHOLD", "3")
    monkeypatch.setenv("AI_ROUTER_BREAKER_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1")
    monkeypatch.setenv("AI_ROUTER_API_KEY", "")

    import importlib
    from app import router_client

    importlib.reload(router_client)

    # Make the real route() fail (httpx raises) — exercises the failure path.
    async def boom_post(*args, **kwargs):
        raise RuntimeError("router down")

    monkeypatch.setattr(router_client.httpx.AsyncClient, "post", boom_post)

    # Three failures trip the breaker.
    for _ in range(3):
        out = await router_client.enhance("condition", {}, {})
        assert out == {}  # nothing merged from a failed router
    assert _breaker_open() is True

    # Replace boom with a success path; the breaker must still short-circuit
    # because we're inside the cooldown. Use the real route() (no patch).
    monkeypatch.setattr(router_client.httpx.AsyncClient, "post",
                        AsyncMock(return_value=_fake_router_response("ok")))
    out = await router_client.enhance("condition", {}, {})
    assert out == {}  # breaker open → router skipped → baseline returned


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets(monkeypatch) -> None:
    """A success closes the breaker — the next failure starts counting again."""
    monkeypatch.setenv("AI_ROUTER_BREAKER_THRESHOLD", "2")
    monkeypatch.setenv("AI_ROUTER_BREAKER_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1")
    monkeypatch.setenv("AI_ROUTER_API_KEY", "")

    import importlib
    from app import router_client

    importlib.reload(router_client)

    async def boom_post(*args, **kwargs):
        raise RuntimeError("router down")

    # 1 failure: breaker not yet open (threshold=2)
    monkeypatch.setattr(router_client.httpx.AsyncClient, "post", boom_post)
    await router_client.enhance("condition", {}, {})
    assert not _breaker_open()

    # A success resets the counter.
    monkeypatch.setattr(router_client.httpx.AsyncClient, "post",
                        AsyncMock(return_value=_fake_router_response("ok")))
    out = await router_client.enhance("condition", {}, {})
    assert out["summary"] == "ok"
    assert not _breaker_open()

    # Two more failures from this point trip the breaker (counter starts at 0).
    monkeypatch.setattr(router_client.httpx.AsyncClient, "post", boom_post)
    await router_client.enhance("condition", {}, {})
    await router_client.enhance("condition", {}, {})
    assert _breaker_open()


def _fake_router_response(content: str):
    """Build a minimal httpx Response-like object for the router happy path.

    The router response is a JSON object whose ``choices[0].message.content``
    is a string containing another JSON object (the per-module result). Both
    layers must be valid JSON.
    """
    import json as _json

    inner = _json.dumps({"summary": content})
    outer = _json.dumps({"choices": [{"message": {"content": inner}}]})

    class _Resp:
        status_code = 200
        content = outer.encode("utf-8")

        def raise_for_status(self):
            return None

        @property
        def text(self) -> str:
            return outer

    return _Resp()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_default_timeout_is_tightened() -> None:
    """The default per-call timeout must be 25s — not 120s.

    A 120s synchronous wait on every inference request would freeze the
    gateway whenever 9Router degrades. 25s is a generous safety ceiling
    well above typical reply times.
    """
    import importlib
    from app import router_client

    importlib.reload(router_client)
    os.environ.pop("AI_ROUTER_TIMEOUT_SECONDS", None)
    assert router_client._router_timeout() == 25


def test_default_timeout_honours_env_override() -> None:
    """Operators can raise the timeout via env when needed (e.g. slow models)."""
    os.environ["AI_ROUTER_TIMEOUT_SECONDS"] = "45"
    import importlib
    from app import router_client

    importlib.reload(router_client)
    assert router_client._router_timeout() == 45
    del os.environ["AI_ROUTER_TIMEOUT_SECONDS"]
