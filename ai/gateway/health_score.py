"""Gateway orchestrating inference + evaluation for vehicle health scoring."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ai.evaluation.scorer import AIScoreResult, evaluate_prediction, fallback_score


class AIVehicleHealthScorer:
    """Score vehicle health using an AI model, falling back deterministically."""

    def __init__(self, model: Optional[Any] = None) -> None:
        self._model = model

    def score(
        self,
        metrics: Dict[str, float],
        vehicle_data: Optional[Dict[str, Any]] = None,
    ) -> AIScoreResult:
        if self._model is None:
            return fallback_score(metrics, "model_not_configured")

        try:
            raw = self._model.predict(metrics, vehicle_data)
        except Exception as exc:  # pragma: no cover - exercised by tests
            return fallback_score(metrics, f"model_exception:{exc}")

        return evaluate_prediction(raw, metrics)