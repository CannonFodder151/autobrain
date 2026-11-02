"""Unit tests for the AI vehicle health module wrapper."""



from ai.app.modules.health_score import AIVehicleHealthScorer, AIScoreResult


class FakeModel:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc

    def predict(self, metrics, vehicle_data=None):
        if self._raise is not None:
            raise self._raise
        return self._response


class TestAIVehicleHealthScorer:
    def test_no_model_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=None)
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is True
        assert result.method == "deterministic_fallback"
        assert result.reason == "model_not_configured"
        assert 0.0 <= result.score <= 100.0
        assert result.confidence == 1.0

    def test_model_exception_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(raise_exc=RuntimeError("boom")))
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is True
        assert "model_exception" in result.reason

    def test_invalid_output_type_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response=42))
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is True
        assert result.reason == "invalid_model_output_type"

    def test_invalid_score_value_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": "not_a_number"}))
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is True
        assert result.reason == "invalid_score_value"

    def test_out_of_range_score_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": 150.0}))
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is True

    def test_valid_ai_result(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": 85.0, "confidence": 0.9}))
        result = scorer.score({"cpu_usage": 50.0})
        assert result.used_fallback is False
        assert result.method == "ai"
        assert result.score == 85.0
        assert result.confidence == 0.9

    def test_default_confidence(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": 70.0}))
        result = scorer.score({})
        assert result.confidence == 1.0

    def test_invalid_confidence_defaults_to_zero(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": 70.0, "confidence": 2.0}))
        result = scorer.score({})
        assert result.confidence == 0.0

    def test_nan_score_uses_fallback(self):
        scorer = AIVehicleHealthScorer(model=FakeModel(response={"score": float("nan")}))
        result = scorer.score({})
        assert result.used_fallback is True

    def test_result_is_dataclass(self):
        r = AIScoreResult(score=50.0, confidence=0.5, used_fallback=False)
        assert r.score == 50.0
        assert r.method == "ai"