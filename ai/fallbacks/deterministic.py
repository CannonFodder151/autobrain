"""Deterministic fallback scorer used when the AI model is unavailable.

Keeps a stable, reproducible score computation that never raises.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.services.health_score import (
    compute_health_score,
    get_health_status,
)


def compute_deterministic_score(
    metrics: Dict[str, float],
    metric_definitions: Optional[list] = None,
) -> dict:
    result = compute_health_score(metrics, metric_definitions)
    return {
        "score": result.score,
        "status": get_health_status(result.score),
        "metrics": result.metrics,
        "details": result.details,
        "method": "deterministic_fallback",
    }


def is_valid_score(value: Any) -> bool:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    import math

    if not math.isfinite(f):
        return False
    return 0.0 <= f <= 100.0