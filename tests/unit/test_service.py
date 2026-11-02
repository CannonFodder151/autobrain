"""Unit tests for backend service (health_score)."""

from backend.app.services.health_score import (
    HealthMetric,
    compute_health_score,
    get_health_status,
    normalize_value,
)


def test_normalize_value_basic():
    assert normalize_value(25, 0, 100) == 0.25


def test_normalize_value_clamps_high():
    assert normalize_value(150, 0, 100) == 1.0


def test_normalize_value_clamps_low():
    assert normalize_value(-10, 0, 100) == 0.0


def test_normalize_value_equal_min_max():
    assert normalize_value(5, 5, 5) == 1.0


def test_compute_zero_total_weight():
    m = [HealthMetric(name="x", value=1, weight=0, min_value=0, max_value=100)]
    r = compute_health_score({"x": 50}, m)
    assert r.score == 100.0
    assert r.metrics == {}


def test_compute_missing_metric_uses_min():
    defs = [HealthMetric(name="x", weight=1.0, min_value=0, max_value=100)]
    r = compute_health_score({}, defs)
    # raw 0 -> normalized 0 -> inverted 1 -> score 100
    assert r.score == 100.0
    assert r.metrics["x"] == 100.0


def test_compute_high_value_lowers_score():
    defs = [HealthMetric(name="x", weight=1.0, min_value=0, max_value=100)]
    r = compute_health_score({"x": 100}, defs)
    assert r.score == 0.0


def test_get_health_status_boundaries():
    assert get_health_status(90) == "healthy"
    assert get_health_status(89.9) == "degraded"
    assert get_health_status(70) == "degraded"
    assert get_health_status(69.9) == "unhealthy"
    assert get_health_status(50) == "unhealthy"
    assert get_health_status(49.9) == "critical"
    assert get_health_status(0) == "critical"
