"""Evaluation of raw AI model outputs into scored results.

Validates and interprets a model's raw prediction, falling back to the
deterministic scorer when the output is missing or malformed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict

from ai.fallbacks.deterministic import compute_deterministic_score


@dataclass
class AIScoreResult:
    score: float
    confidence: float
    used_fallback: bool
    reason: str = ""
    method: str = "ai"


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def fallback_score(metrics: Dict[str, float], reason: str) -> AIScoreResult:
    result = compute_deterministic_score(metrics)
    return AIScoreResult(
        score=result["score"],
        confidence=1.0,
        used_fallback=True,
        reason=reason,
        method="deterministic_fallback",
    )


def evaluate_prediction(raw: Any, metrics: Dict[str, float]) -> AIScoreResult:
    if not isinstance(raw, dict):
        return fallback_score(metrics, "invalid_model_output_type")

    score = raw.get("score")
    confidence = raw.get("confidence", 1.0)

    if not _is_finite_number(score) or not (0.0 <= float(score) <= 100.0):
        return fallback_score(metrics, "invalid_score_value")

    if not _is_finite_number(confidence) or not (0.0 <= float(confidence) <= 1.0):
        confidence = 0.0

    return AIScoreResult(
        score=float(score),
        confidence=float(confidence),
        used_fallback=False,
        method="ai",
    )