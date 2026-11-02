"""Unit tests for the backend health score service."""

import pytest

from backend.app.services.health_score import (
    DEFAULT_METRICS,
    HealthMetric,
    HealthScoreResult,
    compute_health_score,
    get_health_status,
)


class TestComputeHealthScore:
    def test_empty_metrics_returns_full_score(self):
        result = compute_health_score({})
        assert result.score == 100.0
        assert all(v == 100.0 for v in result.metrics.values())
        assert all("raw_value" in d for d in result.details.values())

    def test_zero_total_weight(self):
        definitions = [HealthMetric(name="zero", weight=0.0)]
        result = compute_health_score({}, definitions)
        assert result.score == 100.0

    def test_partial_data(self):
        result = compute_health_score({"cpu_usage": 50.0})
        assert 0.0 <= result.score <= 100.0
        assert "cpu_usage" in result.metrics
        assert "cpu_usage" in result.details

    def test_all_data(self):
        metrics = {
            "cpu_usage": 25.0,
            "memory_usage": 30.0,
            "disk_usage": 40.0,
            "network_latency": 100.0,
            "error_rate": 2.0,
        }
        result = compute_health_score(metrics)
        assert 0.0 <= result.score <= 100.0
        for key in metrics:
            assert key in result.metrics

    def test_score_clamped_to_zero(self):
        metrics = {
            "cpu_usage": 100.0,
            "memory_usage": 100.0,
            "disk_usage": 100.0,
            "network_latency": 500.0,
            "error_rate": 10.0,
        }
        result = compute_health_score(metrics)
        assert result.score >= 0.0
        assert result.score <= 100.0

    def test_score_clamped_to_hundred(self):
        metrics = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "network_latency": 0.0,
            "error_rate": 0.0,
        }
        result = compute_health_score(metrics)
        assert result.score == 100.0

    def test_default_metrics_weights_sum_to_one(self):
        total = sum(m.weight for m in DEFAULT_METRICS)
        assert abs(total - 1.0) < 1e-9

    def test_custom_metric_definitions(self):
        definitions = [
            HealthMetric(name="custom", weight=1.0, min_value=0.0, max_value=10.0),
        ]
        result = compute_health_score({"custom": 10.0}, definitions)
        assert result.score == 0.0  # worst case for inverted metric

    def test_deterministic_reproducibility(self):
        metrics = {"cpu_usage": 42.0, "memory_usage": 55.0}
        r1 = compute_health_score(metrics)
        r2 = compute_health_score(metrics)
        assert r1 == r2

    def test_missing_metric_uses_min_value(self):
        result = compute_health_score({})
        # cpu_usage defaults to min_value=0.0 -> normalized=0 -> inverted=1 -> score=100
        assert result.metrics["cpu_usage"] == 100.0

    def test_details_contain_raw_and_normalized(self):
        result = compute_health_score({"cpu_usage": 50.0})
        detail = result.details["cpu_usage"]
        assert "raw_value" in detail
        assert "normalized" in detail
        assert "score" in detail
        assert "weight" in detail


class TestGetHealthStatus:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (95, "healthy"),
            (90, "healthy"),
            (89, "degraded"),
            (70, "degraded"),
            (69, "unhealthy"),
            (50, "unhealthy"),
            (49, "critical"),
            (0, "critical"),
        ],
    )
    def test_thresholds(self, score, expected):
        assert get_health_status(score) == expected

    def test_returns_string(self):
        assert isinstance(get_health_status(50.0), str)


class TestHealthMetric:
    def test_frozen_dataclass(self):
        m = HealthMetric(name="test", weight=0.5)
        with pytest.raises(Exception):
            m.name = "changed"

    def test_defaults(self):
        m = HealthMetric(name="test", weight=0.5)
        assert m.min_value == 0.0
        assert m.max_value == 100.0


class TestHealthScoreResult:
    def test_frozen_dataclass(self):
        r = HealthScoreResult(score=50.0, metrics={}, details={})
        with pytest.raises(Exception):
            r.score = 60.0