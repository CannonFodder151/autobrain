"""9Router integration client (OpenAI-compatible).

Every AI module reads AI_ROUTER_URL at runtime and POSTs its inference request
to `{AI_ROUTER_URL}/chat/completions` (OpenAI chat-completions format), using
AI_ROUTER_MODEL as the model id. If the router is unreachable, misconfigured,
or returns an error, each module falls back to a deterministic rule-based
implementation so AutoBrain never goes down with the router.

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
    _clean_json,
    _matches_type,
    _validate_nested,
)

logger = get_logger(__name__)


# Backward-compat re-exports (imported from app.router_utils)
_matches_type = _matches_type
_validate_nested = _validate_nested


def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1").rstrip("/")


def router_enabled() -> bool:
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
        return None

    url = f"{router_url()}/chat/completions"
    timeout = int(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "120"))
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AI_ROUTER_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    user_data = f"<untrusted_user_data>\n{json.dumps(payload)}\n</untrusted_user_data>"
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
        return None
    except Exception as exc:
        logger.warning("router_unreachable_using_fallback", module=module, error=str(exc))
        return None


async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    """Deterministic baseline, optionally enriched by 9Router.

    The rule engine runs first and its result is always returned. When the
    router is reachable its response is shallow-merged into the baseline, never
    overwriting deterministic-critical keys (see _AI_IMMUTABLE). model becomes
    ``rule-based+ai`` when the router contributed fields, else the baseline is
    returned untouched. The service stays fully functional with the router down.
    """
    result = await route(module, payload)
    if not isinstance(result, dict):
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
    return merged
