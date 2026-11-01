"""Health score computation service."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class HealthMetric:
    name: str
    value: float
    weight: float
    min_value: float = 0.0
    max_value: float = 100.0


@dataclass(frozen=True)
class HealthScoreResult:
    score: float
    metrics: Dict[str, float]
    details: Dict[str, Dict[str, float]]


DEFAULT_METRICS: List[HealthMetric] = [
    HealthMetric(name="cpu_usage", weight=0.25, min_value=0.0, max_value=100.0),
    HealthMetric(name="memory_usage", weight=0.25, min_value=0.0, max_value=100.0),
    HealthMetric(name="disk_usage", weight=0.20, min_value=0.0, max_value=100.0),
    HealthMetric(name="network_latency", weight=0.15, min_value=0.0, max_value=500.0),
    HealthMetric(name="error_rate", weight=0.15, min_value=0.0, max_value=10.0),
]


def normalize_value(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 1.0
    normalized = (value - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, normalized))


def compute_health_score(
    metrics: Dict[str, float],
    metric_definitions: Optional[List[HealthMetric]] = None,
) -> HealthScoreResult:
    definitions = metric_definitions or DEFAULT_METRICS
    total_weight = sum(m.weight for m in definitions)
    if total_weight == 0:
        return HealthScoreResult(score=100.0, metrics={}, details={})

    metric_scores: Dict[str, float] = {}
    details: Dict[str, Dict[str, float]] = {}
    weighted_sum = 0.0

    for definition in definitions:
        raw_value = metrics.get(definition.name, definition.min_value)
        normalized = normalize_value(raw_value, definition.min_value, definition.max_value)
        inverted = 1.0 - normalized
        metric_score = inverted * 100.0
        metric_scores[definition.name] = metric_score
        details[definition.name] = {
            "raw_value": raw_value,
            "normalized": normalized,
            "score": metric_score,
            "weight": definition.weight,
        }
        weighted_sum += metric_score * definition.weight

    final_score = weighted_sum / total_weight
    return HealthScoreResult(
        score=round(final_score, 2),
        metrics=metric_scores,
        details=details,
    )


def get_health_status(score: float) -> str:
    if score >= 90:
        return "healthy"
    elif score >= 70:
        return "degraded"
    elif score >= 50:
        return "unhealthy"
    else:
        return "critical"