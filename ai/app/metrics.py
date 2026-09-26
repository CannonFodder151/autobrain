"""Prometheus metrics for AI gateway (AUT-3947).

Counters for deterministic vs AI path usage per module.
Exposes /metrics endpoint for Prometheus scraping.
"""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Per-module counters for AI vs deterministic path
AI_DETERMINISTIC_CALLS = Counter(
    "autobrain_ai_deterministic_calls_total",
    "Total deterministic path executions per module",
    ["module"],
)

AI_PATH_COUNTER = Counter(
    "autobrain_ai_path_total",
    "Total AI path executions per module and path type",
    ["module", "path"],
)

AI_ROUTER_ERRORS = Counter(
    "autobrain_ai_router_errors_total",
    "Total router errors per module and status",
    ["module", "status"],
)

# Confidence distribution histogram (bucketed)
AI_CONFIDENCE_HISTOGRAM = Histogram(
    "autobrain_ai_confidence_distribution",
    "AI response confidence distribution per module",
    ["module"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# Reason-tagged fallback counter (why the deterministic path won)
AI_FALLBACK_REASONS = Counter(
    "autobrain_ai_fallback_reasons_total",
    "AI fallback counts per module and reason (router_error, router_disabled, "
    "low_confidence, no_enrichable_fields, router_unavailable, no_usable_result)",
    ["module", "reason"],
)

# --- Recording helpers ---

def record_deterministic(module: str) -> None:
    AI_DETERMINISTIC_CALLS.labels(module=module).inc()
    AI_PATH_COUNTER.labels(module=module, path="deterministic").inc()


def record_hybrid(module: str) -> None:
    AI_PATH_COUNTER.labels(module=module, path="hybrid").inc()


def record_router_error(module: str, status: str) -> None:
    AI_ROUTER_ERRORS.labels(module=module, status=status).inc()
    AI_FALLBACK_REASONS.labels(module=module, reason="router_error").inc()
    AI_PATH_COUNTER.labels(module=module, path="router_error").inc()


def record_confidence(module: str, confidence: float) -> None:
    """Record AI confidence value for histogram."""
    try:
        val = float(confidence)
        if 0.0 <= val <= 1.0:
            AI_CONFIDENCE_HISTOGRAM.labels(module=module).observe(val)
    except (TypeError, ValueError):
        pass


def metrics_bytes() -> bytes:
    """Generate Prometheus exposition format bytes."""
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST