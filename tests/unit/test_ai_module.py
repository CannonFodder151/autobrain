"""Unit tests for AI module."""

from ai.app.modules.health_score import AIVehicleHealthScorer


def _model_returning(payload):
    class M:
        def predict(self, metrics, vehicle_data=None):
            return payload

    return M()


def test_no_model_uses_fallback():
    s = AIVehicleHealthScorer()
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is True
    assert r.method == "deterministic_fallback"


def test_valid_ai_result():
    s = AIVehicleHealthScorer(_model_returning({"score": 77.5, "confidence": 0.9}))
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is False
    assert r.score == 77.5
    assert r.confidence == 0.9


def test_model_raises_uses_fallback():
    class M:
        def predict(self, metrics, vehicle_data=None):
            raise RuntimeError("boom")

    s = AIVehicleHealthScorer(M())
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is True


def test_non_dict_output_uses_fallback():
    s = AIVehicleHealthScorer(_model_returning(42))
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is True


def test_invalid_score_uses_fallback():
    s = AIVehicleHealthScorer(_model_returning({"score": 200, "confidence": 0.5}))
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is True


def test_nan_score_uses_fallback():

    s = AIVehicleHealthScorer(_model_returning({"score": float("nan"), "confidence": 0.5}))
    r = s.score({"cpu_usage": 10})
    assert r.used_fallback is True


def test_confidence_clamped_when_invalid():
    s = AIVehicleHealthScorer(_model_returning({"score": 50, "confidence": 5.0}))
    r = s.score({"cpu_usage": 10})
    assert r.confidence == 0.0
