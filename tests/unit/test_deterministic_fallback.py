"""Unit tests for the deterministic health score fallback."""


import pytest

from ai.app.fallbacks.deterministic import (
    compute_deterministic_score,
    is_valid_score,
)


class TestComputeDeterministicScore:
    """Edge cases: no data, partial data, all data, score clamping, label thresholds."""

    def test_no_data_returns_full_score(self):
        result = compute_deterministic_score({})
        assert result["score"] == 100.0
        assert result["status"] == "healthy"
        assert result["method"] == "deterministic_fallback"

    def test_partial_data(self):
        result = compute_deterministic_score({"cpu_usage": 50.0})
        assert 0.0 <= result["score"] <= 100.0
        assert "cpu_usage" in result["metrics"]

    def test_all_data(self):
        metrics = {
            "cpu_usage": 25.0,
            "memory_usage": 30.0,
            "disk_usage": 40.0,
            "network_latency": 100.0,
            "error_rate": 2.0,
        }
        result = compute_deterministic_score(metrics)
        assert 0.0 <= result["score"] <= 100.0
        for key in metrics:
            assert key in result["metrics"]

    def test_score_clamped_to_zero(self):
        # Max bad values -> score should approach 0 but never go below
        metrics = {
            "cpu_usage": 100.0,
            "memory_usage": 100.0,
            "disk_usage": 100.0,
            "network_latency": 500.0,
            "error_rate": 10.0,
        }
        result = compute_deterministic_score(metrics)
        assert result["score"] >= 0.0
        assert result["score"] <= 100.0

    def test_score_clamped_to_hundred(self):
        # All perfect -> score should be 100
        metrics = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "network_latency": 0.0,
            "error_rate": 0.0,
        }
        result = compute_deterministic_score(metrics)
        assert result["score"] == 100.0

    def test_label_thresholds(self):
        thresholds = [
            (95, "healthy"),
            (90, "healthy"),
            (89, "degraded"),
            (70, "degraded"),
            (69, "unhealthy"),
            (50, "unhealthy"),
            (49, "critical"),
            (30, "critical"),
            (0, "critical"),
        ]
        from backend.app.services.health_score import get_health_status

        for score, expected in thresholds:
            assert get_health_status(score) == expected, f"score={score} expected={expected}"

    def test_custom_metric_definitions(self):
        from backend.app.services.health_score import HealthMetric

        definitions = [
            HealthMetric(name="custom", weight=1.0, min_value=0.0, max_value=10.0),
        ]
        result = compute_deterministic_score({"custom": 10.0}, definitions)
        assert result["score"] == 0.0  # worst case for inverted metric

    def test_zero_total_weight(self):
        from backend.app.services.health_score import HealthMetric

        definitions = [HealthMetric(name="zero", weight=0.0)]
        result = compute_deterministic_score({"zero": 50.0}, definitions)
        assert result["score"] == 100.0

    def test_deterministic_reproducibility(self):
        metrics = {"cpu_usage": 42.0, "memory_usage": 55.0}
        r1 = compute_deterministic_score(metrics)
        r2 = compute_deterministic_score(metrics)
        assert r1 == r2


class TestIsValidScore:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (50.0, True),
            (0.0, True),
            (100.0, True),
            (101.0, False),
            (-1.0, False),
            (float("nan"), False),
            (float("inf"), False),
            ("abc", False),
            (None, False),
            ([], False),
        ],
    )
    def test_valid_score(self, value, expected):
        assert is_valid_score(value) is expected