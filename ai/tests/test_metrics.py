"""Tests for Prometheus-style AI telemetry counters + 9Router cost logging (AUT-3828)."""

import pytest


@pytest.fixture(autouse=True)
def _ai_test_env(monkeypatch):
    # Pin the router to the placeholder so router_enabled() is False and
    # every module path uses its deterministic fallback.
    monkeypatch.setenv("AI_ROUTER_URL", "http://your-9router-instance:port")
    # Disable gateway auth so /v1/telemetry is accessible without a key
    monkeypatch.setenv("AI_GATEWAY_AUTH_DISABLED", "1")


from app.router_client import (  # noqa: E402
    _telemetry_record,
    _record_router_cost,
    ai_cost_snapshot,
    ai_telemetry_reset,
    ai_telemetry_snapshot,
    enhance,
)


@pytest.fixture(autouse=True)
def _reset_counters():
    ai_telemetry_reset()
    yield
    ai_telemetry_reset()


def test_telemetry_records_deterministic_only() -> None:
    _telemetry_record("diagnostics", "deterministic", reason="router_disabled")
    snap = ai_telemetry_snapshot()
    assert snap["diagnostics"]["deterministic_only"] == 1
    assert snap["diagnostics"]["ai_enhanced"] == 0
    assert snap["diagnostics"]["ai_failed_fallback"] == 0


def test_telemetry_records_ai_enhanced() -> None:
    _telemetry_record("service-prediction", "hybrid", confidence=0.95)
    snap = ai_telemetry_snapshot()
    assert snap["service-prediction"]["ai_enhanced"] == 1
    assert snap["service-prediction"]["deterministic_only"] == 0


def test_telemetry_records_ai_failed_fallback() -> None:
    _telemetry_record("resale", "router_error", status=500)
    snap = ai_telemetry_snapshot()
    assert snap["resale"]["ai_failed_fallback"] == 1


def test_telemetry_accumulates_per_module() -> None:
    _telemetry_record("diagnostics", "deterministic", reason="router_disabled")
    _telemetry_record("diagnostics", "deterministic", reason="router_disabled")
    _telemetry_record("diagnostics", "hybrid", confidence=0.9)
    snap = ai_telemetry_snapshot()
    assert snap["diagnostics"]["deterministic_only"] == 2
    assert snap["diagnostics"]["ai_enhanced"] == 1


def test_router_cost_records_tokens() -> None:
    _record_router_cost("diagnostics", {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    })
    snap = ai_cost_snapshot()
    assert snap["diagnostics"]["prompt_tokens"] == 100
    assert snap["diagnostics"]["completion_tokens"] == 50
    assert snap["diagnostics"]["total_tokens"] == 150
    assert snap["diagnostics"]["requests"] == 1


def test_router_cost_accumulates() -> None:
    _record_router_cost("diagnostics", {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
    })
    _record_router_cost("diagnostics", {
        "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30,
    })
    snap = ai_cost_snapshot()
    assert snap["diagnostics"]["prompt_tokens"] == 30
    assert snap["diagnostics"]["completion_tokens"] == 15
    assert snap["diagnostics"]["total_tokens"] == 45
    assert snap["diagnostics"]["requests"] == 2


def test_router_cost_ignores_missing_usage() -> None:
    _record_router_cost("diagnostics", None)
    _record_router_cost("diagnostics", {})
    snap = ai_cost_snapshot()
    assert snap == {}


def test_reset_clears_all_counters() -> None:
    _telemetry_record("diagnostics", "deterministic", reason="router_disabled")
    _record_router_cost("diagnostics", {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8})
    ai_telemetry_reset()
    assert ai_telemetry_snapshot() == {}
    assert ai_cost_snapshot() == {}


@pytest.mark.asyncio
async def test_enhance_deterministic_path_records_counter(monkeypatch) -> None:
    """Router disabled → deterministic_only counter incremented."""
    from unittest.mock import AsyncMock, patch

    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    with patch("app.router_client.route", new=AsyncMock(return_value=None)):
        await enhance("diagnostics", {}, baseline)
    snap = ai_telemetry_snapshot()
    assert snap["diagnostics"]["deterministic_only"] == 1
    assert snap["diagnostics"]["ai_enhanced"] == 0
    assert snap["diagnostics"]["ai_failed_fallback"] == 0


@pytest.mark.asyncio
async def test_enhance_hybrid_path_records_counter(monkeypatch) -> None:
    """Router success → ai_enhanced counter incremented."""
    from unittest.mock import AsyncMock, patch

    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    enriched = {"reason": "mileage-based", "confidence": 0.95}
    with patch("app.router_client.route", new=AsyncMock(return_value=enriched)):
        await enhance("service-prediction", {}, baseline)
    snap = ai_telemetry_snapshot()
    assert snap["service-prediction"]["ai_enhanced"] == 1


@pytest.mark.asyncio
async def test_enhance_router_unavailable_records_counter(monkeypatch) -> None:
    """Router unreachable (route returns None) → deterministic_only counter."""
    from unittest.mock import AsyncMock, patch

    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    with patch("app.router_client.route", new=AsyncMock(return_value=None)):
        await enhance("resale", {}, baseline)
    snap = ai_telemetry_snapshot()
    assert snap["resale"]["deterministic_only"] == 1
    assert snap["resale"]["ai_enhanced"] == 0
    assert snap["resale"]["ai_failed_fallback"] == 0


def test_metrics_endpoint_exposes_counters(monkeypatch) -> None:
    """/metrics returns Prometheus text-format with all counter names."""
    from fastapi.testclient import TestClient

    from app.main import app

    _telemetry_record("diagnostics", "deterministic", reason="router_disabled")
    _telemetry_record("diagnostics", "hybrid", confidence=0.9)
    _telemetry_record("resale", "router_error", status=500)
    _record_router_cost("diagnostics", {
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
    })

    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert 'autobrain_deterministic_only_total{module="diagnostics"} 1' in body
    assert 'autobrain_ai_enhanced_total{module="diagnostics"} 1' in body
    assert 'autobrain_ai_failed_fallback_total{module="resale"} 1' in body
    assert 'autobrain_router_prompt_tokens_total{module="diagnostics"} 10' in body
    assert 'autobrain_router_total_tokens_total{module="diagnostics"} 15' in body
    assert 'autobrain_router_requests_total{module="diagnostics"} 1' in body


def test_confidence_histogram_buckets() -> None:
    """Confidence values land in the right 0.1 bucket (AUT-3947)."""
    from app.router_client import _record_confidence, ai_confidence_snapshot

    _record_confidence("diagnostics", 0.95)  # bucket 9 (0.9-1.0)
    _record_confidence("diagnostics", 0.42)  # bucket 4 (0.4-0.5)
    _record_confidence("diagnostics", 0.0)   # bucket 0 (0.0-0.1)
    _record_confidence("diagnostics", 1.0)   # bucket 9
    snap = ai_confidence_snapshot()
    buckets = snap["diagnostics"]["buckets"]
    assert buckets[0] == 1
    assert buckets[4] == 1
    assert buckets[9] == 2
    assert sum(buckets) == 4
    assert snap["diagnostics"]["sum"] == 2.37


def test_confidence_histogram_clamps_and_ignores_bad() -> None:
    """Out-of-range values are ignored, never recorded (AUT-3947)."""
    from app.router_client import _record_confidence, ai_confidence_snapshot

    _record_confidence("diagnostics", 1.5)
    _record_confidence("diagnostics", -0.1)
    _record_confidence("diagnostics", "high")
    assert ai_confidence_snapshot() == {}


def test_metrics_endpoint_exposes_confidence_histogram() -> None:
    """/metrics emits the confidence histogram + sum/count (AUT-3947)."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.router_client import _record_confidence

    _record_confidence("diagnostics", 0.95)
    _record_confidence("diagnostics", 0.42)

    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert 'autobrain_ai_confidence_bucket{module="diagnostics",le="1.0"} 2' in body
    assert 'autobrain_ai_confidence_bucket{module="diagnostics",le="+Inf"} 2' in body
    assert 'autobrain_ai_confidence_count{module="diagnostics"} 2' in body
    assert 'autobrain_ai_confidence_sum{module="diagnostics"} 1.37' in body


def test_telemetry_endpoint_includes_confidence_and_cost() -> None:
    """/v1/telemetry now returns confidence + cost snapshots (AUT-3947)."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.router_client import _record_confidence, _record_router_cost

    _record_confidence("diagnostics", 0.9)
    _record_router_cost("diagnostics", {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8})

    with TestClient(app) as client:
        resp = client.get("/v1/telemetry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"]["diagnostics"]["buckets"][9] == 1
    assert body["cost"]["diagnostics"]["total_tokens"] == 8
    assert body["cost"]["diagnostics"]["requests"] == 1