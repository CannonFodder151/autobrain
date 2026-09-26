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

from app.logging import get_logger
from app.router_utils import (
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


# --- AI vs deterministic telemetry (AUT-3813, AUT-3828, AUT-3947) -------------
# In-process counters for AI vs deterministic path usage per module.
# Keys: deterministic_only, ai_enhanced, ai_failed_fallback.
# Reset on process start; for long-lived services, restart or read cumulative log lines.
_AI_TELEMETRY: dict[str, dict[str, int]] = {}

# Confidence histogram buckets for AI responses (AUT-3947).
# 10 buckets: [0.0-0.1, 0.1-0.2, ..., 0.9-1.0]
_AI_CONFIDENCE_BUCKETS: dict[str, list[int]] = {}

# Running sum of recorded confidences, for the Prometheus _sum series.
_AI_CONFIDENCE_SUM: dict[str, float] = {}

# 9Router token usage & request count per module (AUT-3828).
_AI_COST: dict[str, dict[str, int]] = {}


def _telemetry_record(module: str, path: str, **extra) -> None:
    """Record one inference-path decision for later audit.

    path is one of: ``deterministic`` (router down / low confidence / no
    enrichable fields), ``hybrid`` (router enriched the baseline), or
    ``router_error`` (router returned an error and we fell back).
    """
    # Map internal path names to snapshot/reporting names
    path_map = {
        "deterministic": "deterministic_only",
        "hybrid": "ai_enhanced",
        "router_error": "ai_failed_fallback",
    }
    snap_key = path_map.get(path, path)
    bucket = _AI_TELEMETRY.setdefault(module, {"deterministic_only": 0, "ai_enhanced": 0, "ai_failed_fallback": 0})
    bucket[snap_key] = bucket.get(snap_key, 0) + 1
    logger.info("ai_path", module=module, path=path, **extra)


def _record_confidence(module: str, confidence: float) -> None:
    """Record AI confidence into histogram buckets (AUT-3947)."""
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        return
    bucket_idx = min(int(confidence * 10), 9)
    buckets = _AI_CONFIDENCE_BUCKETS.setdefault(module, [0] * 10)
    buckets[bucket_idx] += 1
    _AI_CONFIDENCE_SUM[module] = _AI_CONFIDENCE_SUM.get(module, 0.0) + confidence


def _record_router_cost(module: str, usage: dict | None) -> None:
    """Record 9Router token usage from a successful response (AUT-3828)."""
    if not usage or not isinstance(usage, dict):
        return
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    total = int(usage.get("total_tokens", 0))
    if prompt == 0 and completion == 0 and total == 0:
        return
    cost = _AI_COST.setdefault(module, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0})
    cost["prompt_tokens"] += prompt
    cost["completion_tokens"] += completion
    cost["total_tokens"] += total
    cost["requests"] += 1


def ai_telemetry_snapshot() -> dict[str, dict[str, int]]:
    """Return a copy of the current telemetry counters (for /v1/telemetry)."""
    return {m: dict(c) for m, c in _AI_TELEMETRY.items()}


def ai_cost_snapshot() -> dict[str, dict[str, int]]:
    """Return a copy of the 9Router token-usage counters."""
    return {m: dict(c) for m, c in _AI_COST.items()}


def ai_confidence_snapshot() -> dict[str, dict[str, object]]:
    """Return a copy of the AI confidence histogram buckets + sum per module."""
    return {m: {"buckets": list(b), "sum": _AI_CONFIDENCE_SUM.get(m, 0.0)} for m, b in _AI_CONFIDENCE_BUCKETS.items()}


def ai_telemetry_reset() -> None:
    """Clear all telemetry counters (admin endpoint)."""
    _AI_TELEMETRY.clear()
    _AI_CONFIDENCE_BUCKETS.clear()
    _AI_CONFIDENCE_SUM.clear()
    _AI_COST.clear()


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
    Telemetry is recorded by the caller (enhance) so each inference is counted once.
    """
    if not router_enabled():
        logger.info("router_disabled_using_fallback", module=module)
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
            usage = data.get("usage")
            if usage:
                _record_router_cost(module, usage)
            logger.info("router_response", module=module, model=router_model(), status=resp.status_code)
            return result
    except httpx.HTTPStatusError as exc:
        logger.warning("router_http_error", module=module, status=exc.response.status_code)
        return None
    except Exception as exc:
        logger.warning("router_unreachable_using_fallback", module=module, error=str(exc))
        return None


async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    """Deterministic baseline, optionally enriched by 9Router.

    The rule engine runs first and its result is always returned. When the
    router is reachable its response is shallow-merged into the baseline, never
    overwriting deterministic-critical keys (see _AI_IMMUTABLE). The router
    response must include a "confidence" field (0-1); only fields from responses
    with confidence >= MIN_AI_CONFIDENCE are merged. model becomes
    ``rule-based+ai`` when the router contributed fields, else the baseline is
    returned untouched. The service stays fully functional with the router down.
    """
    min_confidence = float(os.getenv("MIN_AI_CONFIDENCE", "0.75"))
    result = await route(module, payload)
    if not isinstance(result, dict):
        _telemetry_record(module, "deterministic", reason="router_unavailable")
        return baseline

    confidence = result.get("confidence")
    try:
        conf_val = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        conf_val = 0.0

    _record_confidence(module, conf_val)

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
        _telemetry_record(module, "deterministic", reason="no_enrichable_fields", confidence=conf_val)
    return merged
