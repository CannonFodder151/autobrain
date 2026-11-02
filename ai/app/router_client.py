"""9Router integration client (OpenAI-compatible).

HTTP transport layer. All configuration (system prompts, schemas, payload
caps, validation) lives in ``app.router_utils`` so this module only owns:
  * env-var lookups (router_url, router_enabled, router_model)
  * the request/response cycle (route)
  * the deterministic-first merge into the baseline (enhance)

If the router is unreachable, misconfigured, or returns an error, callers
fall back to their deterministic rule-based implementation so AutoBrain
never goes down with the router.

Environment variables:
  AI_ROUTER_URL              e.g. http://10.0.3.17:20128/v1
  AI_ROUTER_API_KEY          optional bearer key
  AI_ROUTER_MODEL            model id served by the router (default General-Use)
  AI_ROUTER_TIMEOUT_SECONDS  per-request timeout
"""

import json
import os

import httpx

from .logging import get_logger
from .router_utils import (
    _AI_IMMUTABLE,
    _MAX_ROUTER_RESPONSE_BYTES,
    _SCHEMAS,
    _SYSTEM_PROMPTS,
    _TEMPERATURES,
    _UNTRUSTED_DATA_INSTRUCTION,
    _cap_payload,
    _clean_json,
    _matches_type,
    _validate_nested,
)

logger = get_logger(__name__)


# Backward-compat re-exports (imported from app.router_utils)
# Existing callers may still import these names from app.router_client.
_cap_payload = _cap_payload
_matches_type = _matches_type
_validate_nested = _validate_nested


# --- AI vs deterministic telemetry (AUT-3813) -------------------------------
# In-process counters so operators can grep the logs for ai_path events and
# compute the hybrid/deterministic split per module without a separate
# metrics store. Reset on process start; for long-lived services, restart or
# read the cumulative log lines.
_AI_TELEMETRY: dict[str, dict[str, int]] = {}

# --- AI cost tracking (AUT-6646) -------------------------------------------
# Rough cost estimates per module based on typical token usage and 9Router pricing.
# These are ORDER-OF-MAGNITUDE estimates for guardrails, not precise billing.
_MODULE_COST_ESTIMATES: dict[str, float] = {
    "diagnostics": 0.002,
    "service-prediction": 0.0015,
    "ocr": 0.003,
    "fuel-ocr": 0.002,
    "odometer": 0.002,
    "resale": 0.002,
    "mod-impact": 0.0015,
    "condition": 0.001,
    "parts-guide": 0.002,
    "advisor": 0.003,
    "car-check": 0.002,
    "social-image": 0.001,
}

_COST_TRACKING: dict[str, dict[str, float]] = {}


def _cost_tracking_record(module: str, path: str, estimated_cost: float = 0.0) -> None:
    """Record an inference call with estimated cost."""
    bucket = _COST_TRACKING.setdefault(module, {"calls": 0, "ai_calls": 0, "estimated_cost_usd": 0.0})
    bucket["calls"] = bucket.get("calls", 0) + 1
    if path == "hybrid":
        bucket["ai_calls"] = bucket.get("ai_calls", 0) + 1
        bucket["estimated_cost_usd"] = bucket.get("estimated_cost_usd", 0.0) + estimated_cost
    elif path == "router_error":
        pass  # No cost for errors


def _cost_tracking_snapshot() -> dict[str, dict[str, float]]:
    """Return a copy of the current cost tracking counters."""
    return {m: dict(c) for m, c in _COST_TRACKING.items()}


def _cost_tracking_reset() -> None:
    """Clear all cost tracking counters (admin endpoint)."""
    _COST_TRACKING.clear()


def _telemetry_record(module: str, path: str, **extra) -> None:
    """Record one inference-path decision for later audit.

    path is one of: ``deterministic`` (router down / low confidence / no
    enrichable fields), ``hybrid`` (router enriched the baseline), or
    ``router_error`` (router returned an error and we fell back).
    """
    bucket = _AI_TELEMETRY.setdefault(module, {"deterministic": 0, "hybrid": 0, "router_error": 0})
    bucket[path] = bucket.get(path, 0) + 1
    # Also record cost tracking
    estimated_cost = _MODULE_COST_ESTIMATES.get(module, 0.0) if path == "hybrid" else 0.0
    _cost_tracking_record(module, path, estimated_cost)
    logger.info("ai_path", module=module, path=path, **extra)


def ai_telemetry_snapshot() -> dict[str, dict[str, int]]:
    """Return a copy of the current telemetry counters (for /v1/telemetry)."""
    return {m: dict(c) for m, c in _AI_TELEMETRY.items()}


def ai_telemetry_reset() -> None:
    """Clear all telemetry counters (admin endpoint)."""
    _AI_TELEMETRY.clear()


def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1").rstrip("/")


def router_enabled() -> bool:
    """Return True when the AI router should be called.

    Three conditions must all hold:
      1. ``AI_ENABLED`` is not explicitly set to ``false`` / ``0``.
      2. ``AI_ROUTER_URL`` is configured and not the placeholder.
    Setting ``AI_ENABLED=false`` forces every module into deterministic-only
    mode — useful for cost control, incident response, or offline deploys.
    """
    ai_enabled = os.getenv("AI_ENABLED", "true").strip().lower()
    if ai_enabled in ("false", "0", "no"):
        return False
    url = router_url()
    return bool(url) and "your-9router-instance" not in url


def router_model() -> str:
    return os.getenv("AI_ROUTER_MODEL", "General-Use")


async def route(module: str, payload: dict) -> dict | None:
    """POST an OpenAI-style chat completion to 9Router.

    Returns the parsed result dict, or None on any failure (callers fall back).
    """
    if not router_enabled():
        logger.info("router_disabled_using_fallback", module=module)
        _telemetry_record(module, "deterministic", reason="router_disabled")
        return None

    url = f"{router_url()}/chat/completions"
    timeout = int(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "120"))
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AI_ROUTER_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    user_data = f"<untrusted_user_data>\n{json.dumps(_cap_payload(payload, logger=logger))}\n</untrusted_user_data>"
    body = {
        "model": router_model(),
        "stream": False,
        "temperature": _TEMPERATURES.get(module, 0.0),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPTS.get(module, "Return STRICT JSON.")},
            {"role": "system", "content": _UNTRUSTED_DATA_INSTRUCTION},
            {"role": "user", "content": user_data},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            if len(resp.content) > _MAX_ROUTER_RESPONSE_BYTES:
                logger.warning("router_response_oversized", module=module, size=len(resp.content))
                return None
            data = _clean_json(resp.text)
            content = data["choices"][0]["message"]["content"]
            result = _clean_json(content)
            result.setdefault("model", router_model())
            logger.info("router_response", module=module, model=router_model(), status=resp.status_code)
            return result
    except httpx.HTTPStatusError as exc:
        logger.warning("router_http_error", module=module, status=exc.response.status_code)
        _telemetry_record(module, "router_error", status=exc.response.status_code)
        return None
    except Exception as exc:
        logger.warning("router_unreachable_using_fallback", module=module, error=str(exc))
        _telemetry_record(module, "router_error", error=str(exc))
        return None


# Per-module minimum confidence floors (can be overridden via env MIN_AI_CONFIDENCE_<MODULE>)
# Higher floors for safety-critical or high-cost modules
_MODULE_CONFIDENCE_FLOORS: dict[str, float] = {
    "diagnostics": 0.85,
    "service-prediction": 0.85,
    "ocr": 0.80,
    "fuel-ocr": 0.80,
    "odometer": 0.90,
    "resale": 0.80,
    "mod-impact": 0.80,
    "condition": 0.75,
    "parts-guide": 0.75,
    "advisor": 0.85,
    "car-check": 0.85,
    "social-image": 0.70,
}


def _get_module_confidence_floor(module: str) -> float:
    """Get the minimum confidence floor for a module, with env override support."""
    env_key = f"MIN_AI_CONFIDENCE_{module.upper().replace('-', '_')}"
    env_val = os.getenv(env_key)
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return _MODULE_CONFIDENCE_FLOORS.get(module, float(os.getenv("MIN_AI_CONFIDENCE", "0.85")))


async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    """Deterministic baseline, optionally enriched by 9Router.

    The rule engine runs first and its result is always returned. When the
    router is reachable its response is shallow-merged into the baseline, never
    overwriting deterministic-critical keys (see _AI_IMMUTABLE). The router
    response must include a "confidence" field (0-1); only fields from responses
    with confidence >= module-specific floor are merged. model becomes
    ``rule-based+ai`` when the router contributed fields, else the baseline is
    returned untouched. The service stays fully functional with the router down.
    """
    min_confidence = _get_module_confidence_floor(module)
    result = await route(module, payload)
    if not isinstance(result, dict):
        _telemetry_record(module, "deterministic", reason="router_unavailable")
        return baseline

    confidence = result.get("confidence")
    try:
        conf_val = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        conf_val = 0.0

    if conf_val < min_confidence:
        _telemetry_record(module, "deterministic", reason="low_confidence", confidence=conf_val, threshold=min_confidence)
        return baseline

    immutable = _AI_IMMUTABLE.get(module, frozenset())
    schema = _SCHEMAS.get(module, {})
    merged = dict(baseline)
    enriched = False
    for key, value in result.items():
        if key == "model" or key in immutable:
            continue
        if key not in schema or not _matches_type(value, schema[key]):
            logger.warning("router_dropped_key", module=module, key=key)
            continue
        if not _validate_nested(value):
            logger.warning("router_dropped_key_nested", module=module, key=key)
            continue
        merged[key] = value
        enriched = True
    if enriched:
        merged["model"] = "rule-based+ai"
        _telemetry_record(module, "hybrid", confidence=conf_val)
    else:
        _telemetry_record(module, "deterministic", reason="no_enrichable_fields")
    return merged


# Exports for AI gateway endpoints
__all__ = [
    "router_url",
    "router_enabled",
    "router_model",
    "route",
    "enhance",
    "ai_telemetry_snapshot",
    "ai_telemetry_reset",
    "_cost_tracking_snapshot",
    "_cost_tracking_reset",
]
