"""Tests for AUT-3947: Prometheus metrics for AI vs deterministic split.

Verifies the /metrics endpoint and that the counters in router_client
increment deterministically when a module takes the deterministic or hybrid path.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.metrics import (
    AI_CONFIDENCE_HISTOGRAM,
    AI_DETERMINISTIC_CALLS,
    AI_FALLBACK_REASONS,
    AI_PATH_COUNTER,
    AI_ROUTER_ERRORS,
)
from app.router_client import _AI_TELEMETRY, _telemetry_record

client = TestClient(app)

BOGUS_ROUTER = "http://your-9router-instance:port/v1"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AI_ROUTER_URL", BOGUS_ROUTER)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "correct-secret")
    monkeypatch.delenv("AI_GATEWAY_AUTH_DISABLED", raising=False)


_METRICS = (AI_DETERMINISTIC_CALLS, AI_FALLBACK_REASONS, AI_PATH_COUNTER,
            AI_ROUTER_ERRORS, AI_CONFIDENCE_HISTOGRAM)


@pytest.fixture(autouse=True)
def _reset_counters():
    def _clear():
        for m in _METRICS:
            for s in list(m._metrics.keys()):
                m.remove(*s)
        _AI_TELEMETRY.clear()

    _clear()
    yield
    _clear()


def _sample_text(body: bytes) -> str:
    return body.decode("utf-8")


def test_metrics_endpoint_scrapeable_without_auth():
    """Prometheus scrapes without a bearer key; /v1/* still requires one."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_returns_prometheus_format():
    resp = client.get("/metrics", headers={"Authorization": "Bearer correct-secret"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = _sample_text(resp.content)
    # The endpoint must expose the AI-vs-deterministic split series.
    assert "autobrain_ai_deterministic_calls_total" in text
    assert "autobrain_ai_fallback_reasons_total" in text
    assert "autobrain_ai_path_total" in text
    assert "autobrain_ai_router_errors_total" in text
    assert "autobrain_ai_confidence_distribution" in text


def test_deterministic_record_increments_counters():
    _telemetry_record("resale", "deterministic", reason="low_confidence", confidence=0.0)
    text = _sample_text(client.get("/metrics", headers={"Authorization": "Bearer correct-secret"}).content)
    assert 'autobrain_ai_deterministic_calls_total{module="resale"} 1' in text
    assert 'autobrain_ai_path_total{module="resale",path="deterministic"} 1' in text
    assert 'autobrain_ai_fallback_reasons_total{module="resale",reason="low_confidence"} 1' in text
    # confidence 0.0 falls in all buckets >= 0.0
    assert 'autobrain_ai_confidence_distribution_bucket{le="0.0",module="resale"} 1' in text
    assert 'autobrain_ai_confidence_distribution_bucket{le="1.0",module="resale"} 1' in text
    assert 'autobrain_ai_confidence_distribution_count{module="resale"} 1' in text
    assert 'autobrain_ai_confidence_distribution_sum{module="resale"} 0.0' in text


def test_hybrid_record_increments_path_counter():
    _telemetry_record("diagnostics", "hybrid", confidence=0.95)
    text = _sample_text(client.get("/metrics", headers={"Authorization": "Bearer correct-secret"}).content)
    assert 'autobrain_ai_path_total{module="diagnostics",path="hybrid"} 1' in text
    assert 'autobrain_ai_deterministic_calls_total{module="diagnostics"}' not in text
    # confidence 0.95 lands in the 1.0 and +Inf buckets (Prometheus histograms are cumulative)
    assert 'autobrain_ai_confidence_distribution_bucket{le="1.0",module="diagnostics"} 1' in text
    assert 'autobrain_ai_confidence_distribution_bucket{le="+Inf",module="diagnostics"} 1' in text
    assert 'autobrain_ai_confidence_distribution_count{module="diagnostics"} 1' in text
    assert 'autobrain_ai_confidence_distribution_sum{module="diagnostics"} 0.95' in text


def test_router_error_record_increments_error_counter():
    _telemetry_record("ocr", "router_error", status=503)
    text = _sample_text(client.get("/metrics", headers={"Authorization": "Bearer correct-secret"}).content)
    assert 'autobrain_ai_router_errors_total{module="ocr",status="503"} 1' in text
    assert 'autobrain_ai_path_total{module="ocr",path="router_error"} 1' in text
    assert 'autobrain_ai_fallback_reasons_total{module="ocr",reason="router_error"} 1' in text


def test_confidence_out_of_range_is_ignored():
    _telemetry_record("resale", "hybrid", confidence=1.5)
    text = _sample_text(client.get("/metrics", headers={"Authorization": "Bearer correct-secret"}).content)
    # No confidence buckets should have been recorded for this call.
    assert 'autobrain_ai_confidence_distribution_bucket{module="resale",le="1.0"}' not in text