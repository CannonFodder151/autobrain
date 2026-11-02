"""AI-driven service prediction module with deterministic baseline first."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai.fallbacks.deterministic import compute_deterministic_score


# _AI_IMMUTABLE: This module is marked immutable to prevent AI modification
# of the service prediction logic which must remain deterministic and auditable.
_AI_IMMUTABLE = True


@dataclass
class AIScoreResult:
    score: float
    confidence: float
    used_fallback: bool
    reason: str = ""
    method: str = "ai"


class AIServicePredictionScorer:
    """Score service prediction: deterministic baseline first, AI as fallback."""

    def __init__(self, model: Optional[Any] = None) -> None:
        self._model = model

    def score(
        self,
        metrics: Dict[str, float],
        vehicle_data: Optional[Dict[str, Any]] = None,
    ) -> AIScoreResult:
        # Deterministic baseline runs first.
        baseline = compute_deterministic_score(metrics)

        if self._model is None:
            return self._fallback_result(baseline, "model_not_configured")

        try:
            raw = self._model.predict(metrics, vehicle_data)
        except Exception as exc:
            return self._fallback_result(baseline, f"model_exception:{exc}")

        result = self._interpret(raw)
        if result.used_fallback:
            return self._fallback_result(baseline, result.reason)
        return result

    def _interpret(self, raw: Any) -> AIScoreResult:
        if not isinstance(raw, dict):
            return AIScoreResult(
                score=0.0,
                confidence=0.0,
                used_fallback=True,
                reason="invalid_model_output_type",
            )

        score = raw.get("score")
        confidence = raw.get("confidence", 1.0)

        if not _is_finite_number(score) or not (0.0 <= float(score) <= 100.0):
            return AIScoreResult(
                score=0.0,
                confidence=0.0,
                used_fallback=True,
                reason="invalid_score_value",
            )
        if not _is_finite_number(confidence) or not (0.0 <= float(confidence) <= 1.0):
            confidence = 0.0

        return AIScoreResult(
            score=float(score),
            confidence=float(confidence),
            used_fallback=False,
            method="ai",
        )

    def _fallback_result(
        self, baseline: dict, reason: str
    ) -> AIScoreResult:
        return AIScoreResult(
            score=baseline["score"],
            confidence=1.0,
            used_fallback=True,
            reason=reason,
            method="deterministic_fallback",
        )


def _is_finite_number(value: Any) -> bool:
    import math
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False