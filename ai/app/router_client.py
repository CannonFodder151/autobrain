"""9Router integration client (OpenAI-compatible).

HTTP transport layer. All configuration (system prompts, schemas, payload
caps, validation) lives in ``app.router_utils`` so this module only owns:
  * env-var lookups (router_url, router_enabled, router_model)
  * the request/response cycle (route)
  * the deterministic-first merge into the baseline (enhance)

If the router is unreachable, misconfigured, or returns an error, callers
fall back to their deterministic rule-based implementation so AutoBrain
never goes down with the router.

Reliability safeguards ("less AI, more reliable"):

  * Per-call timeout (AI_ROUTER_TIMEOUT_SECONDS, default 25s) — a slow router
    can never block an inference request indefinitely. Typical 9Router replies
    land in 3-8s; 25s is a generous safety ceiling, not the working budget.
  * Circuit breaker: after a small number of consecutive failures the gateway
    short-circuits the router for a cooldown window (defaults: 3 failures ->
    60s open). This stops a degraded router from adding latency to every
    request in the fleet — the deterministic baseline stays available.
  * Response size cap (1 MiB) + nested depth/length validation protect the
    service from runaway model output and injection-style JSON.

Environment variables:
  AI_ROUTER_URL                       e.g. http://10.0.3.17:20128/v1
  AI_ROUTER_API_KEY                   optional bearer key
  AI_ROUTER_MODEL                     model id served by the router (default General-Use)
  AI_ROUTER_TIMEOUT_SECONDS           per-request timeout (default 25)
  AI_ROUTER_BREAKER_THRESHOLD         consecutive failures to open breaker (default 3)
  AI_ROUTER_BREAKER_COOLDOWN_SECONDS  how long the breaker stays open (default 60)
"""

import json
import os
import threading
import time

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


def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1").rstrip("/")


def router_enabled() -> bool:
    url = router_url()
    return bool(url) and "your-9router-instance" not in url


def router_model() -> str:
    return os.getenv("AI_ROUTER_MODEL", "General-Use")


def _router_timeout() -> int:
    try:
        return max(1, int(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "25")))
    except ValueError:
        return 25


# Circuit breaker: after N consecutive failures the router is short-circuited
# for COOLDOWN_SECONDS. Reset on the first success. Single-process state is
# fine — the AI gateway runs in one uvicorn per container and the breaker is a
# coarse guard against a degraded router, not a global health check.
_BREAKER_LOCK = threading.Lock()
_BREAKER_FAILURES = 0
_BREAKER_OPEN_UNTIL = 0.0


def _breaker_threshold() -> int:
    try:
        return max(1, int(os.getenv("AI_ROUTER_BREAKER_THRESHOLD", "3")))
    except ValueError:
        return 3


def _breaker_cooldown_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("AI_ROUTER_BREAKER_COOLDOWN_SECONDS", "60")))
    except ValueError:
        return 60.0


def _breaker_open() -> bool:
    """True while the breaker is open and the router should be skipped."""
    global _BREAKER_OPEN_UNTIL
    with _BREAKER_LOCK:
        if _BREAKER_OPEN_UNTIL and time.monotonic() < _BREAKER_OPEN_UNTIL:
            return True
        if _BREAKER_OPEN_UNTIL and time.monotonic() >= _BREAKER_OPEN_UNTIL:
            _BREAKER_OPEN_UNTIL = 0.0
        return False


def _breaker_record_success() -> None:
    global _BREAKER_FAILURES, _BREAKER_OPEN_UNTIL
    with _BREAKER_LOCK:
        _BREAKER_FAILURES = 0
        _BREAKER_OPEN_UNTIL = 0.0


def _breaker_record_failure() -> None:
    global _BREAKER_FAILURES, _BREAKER_OPEN_UNTIL
    cooldown = _breaker_cooldown_seconds()
    if cooldown <= 0:
        return
    threshold = _breaker_threshold()
    with _BREAKER_LOCK:
        _BREAKER_FAILURES += 1
        if _BREAKER_FAILURES >= threshold and _BREAKER_OPEN_UNTIL == 0.0:
            _BREAKER_OPEN_UNTIL = time.monotonic() + cooldown
            logger.warning(
                "router_circuit_open",
                consecutive_failures=_BREAKER_FAILURES,
                cooldown_seconds=cooldown,
                threshold=threshold,
            )


def reset_circuit_breaker() -> None:
    """Test/admin hook: force the breaker closed."""
    global _BREAKER_FAILURES, _BREAKER_OPEN_UNTIL
    with _BREAKER_LOCK:
        _BREAKER_FAILURES = 0
        _BREAKER_OPEN_UNTIL = 0.0


async def route(module: str, payload: dict) -> dict | None:
    """POST an OpenAI-style chat completion to 9Router.

    Returns the parsed result dict, or None on any failure (callers fall back).
    Honours the per-call timeout, response-size cap, and the circuit breaker —
    a slow or down router never adds latency to the inference request and the
    deterministic baseline always wins on the breaker-open path.
    """
    if not router_enabled():
        logger.info("router_disabled_using_fallback", module=module)
        return None
    if _breaker_open():
        logger.info("router_circuit_open_using_fallback", module=module)
        return None

    url = f"{router_url()}/chat/completions"
    timeout = _router_timeout()
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
                _breaker_record_failure()
                return None
            data = _clean_json(resp.text)
            content = data["choices"][0]["message"]["content"]
            result = _clean_json(content)
            result.setdefault("model", router_model())
            logger.info("router_response", module=module, model=router_model(), status=resp.status_code)
            _breaker_record_success()
            return result
    except httpx.HTTPStatusError as exc:
        logger.warning("router_http_error", module=module, status=exc.response.status_code)
        _breaker_record_failure()
        return None
    except Exception as exc:
        logger.warning("router_unreachable_using_fallback", module=module, error=str(exc))
        _breaker_record_failure()
        return None


# Modules where the router's job is per-item refinement that the deterministic
# baseline deliberately leaves for the AI (description / brand / category tidy,
# item classification). The baseline cannot "already contain" these refinements
# without duplicating the AI work, so the short-circuit is bypassed for them.
_NEVER_SHORT_CIRCUIT = frozenset({"parts-guide"})


def _ai_can_contribute(module: str, baseline: dict, schema: dict) -> bool:
    """True if the router could plausibly add a new field to ``baseline``.

    Returns False when every schema key the router is allowed to write is
    already populated in the baseline — calling the router would be wasted
    work, and the deterministic-first contract is fully satisfied by the
    baseline alone. The short-circuit never runs for modules in
    ``_NEVER_SHORT_CIRCUIT`` (their AI work is per-item, not top-level).
    """
    if module in _NEVER_SHORT_CIRCUIT:
        return True
    if not schema:
        return True
    immutable = _AI_IMMUTABLE.get(module, frozenset())
    for key in schema:
        if key in immutable or key == "model":
            continue
        val = baseline.get(key)
        if val is None:
            return True
        if isinstance(val, (list, dict)) and len(val) == 0:
            return True
        if isinstance(val, str) and not val.strip():
            return True
    return False


async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    """Deterministic baseline, optionally enriched by 9Router.

    The rule engine runs first and its result is always returned. When the
    router is reachable its response is shallow-merged into the baseline, never
    overwriting deterministic-critical keys (see _AI_IMMUTABLE). model becomes
    ``rule-based+ai`` when the router contributed fields, else the baseline is
    returned untouched. The service stays fully functional with the router down.

    Short-circuit: when the deterministic baseline already satisfies every
    "AI-addable" schema field (i.e. there is nothing the router could enrich
    that the baseline does not already cover with a non-empty value), the
    router is skipped entirely. No network call, no quota burn, no added
    latency for an enrichment that cannot change the result. Modules that need
    the router for per-item refinement (``parts-guide``) bypass the
    short-circuit.
    """
    schema = _SCHEMAS.get(module, {})
    if not _ai_can_contribute(module, baseline, schema):
        return baseline

    result = await route(module, payload)
    if not isinstance(result, dict):
        return baseline

    immutable = _AI_IMMUTABLE.get(module, frozenset())
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
    return merged