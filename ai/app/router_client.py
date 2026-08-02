"""9Router integration client (OpenAI-compatible).

Every AI module reads AI_ROUTER_URL at runtime and POSTs its inference request
to `{AI_ROUTER_URL}/chat/completions` (OpenAI chat-completions format), using
AI_ROUTER_MODEL as the model id. If the router is unreachable, misconfigured,
or returns an error, each module falls back to a deterministic rule-based
implementation so AutoBrain never goes down with the router.

Environment variables:
  AI_ROUTER_URL              e.g. http://your-9router-instance:port/v1
  AI_ROUTER_API_KEY          optional bearer key
  AI_ROUTER_MODEL            model id served by the router (default General-Use)
  AI_ROUTER_TIMEOUT_SECONDS  per-request timeout
"""

import json
import os
from datetime import date

import httpx

from app.logging import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPTS: dict[str, str] = {
    "diagnostics": (
        "You are AutoBrain's automotive diagnostic engine for car enthusiasts. "
        "Given vehicle context, symptoms and OBD codes, diagnose likely causes. "
        'Return STRICT JSON (no markdown, no prose outside the object): '
        '{"summary": string, "severity": "low"|"medium"|"high"|"critical", '
        '"estimated_cost": number|null, "cost_range": [number, number]|null, '
        '"items": [{"cause": string, "confidence": number (0-1), "severity": string, '
        '"parts_needed": [string], "repair_notes": string, '
        '"estimated_cost": number|null}], '
        '"parts_needed": [string], "recommended_actions": [string]}'
    ),
    "service-prediction": (
        "You are an automotive maintenance scheduler. Using the manufacturer "
        "service interval for the given make/model and service type, plus the "
        "current odometer and last service, compute the next service due. "
        "Today's date is " + date.today().isoformat() + ". "
        'Return STRICT JSON: {"service_type": string, "interval_km": int, '
        '"interval_months": int, "due_in_km": int, "due_in_days": int, '
        '"next_due_km": int, "next_due_date": "YYYY-MM-DD", '
        '"confidence": number (0-1), "reason": string}'
    ),
    "ocr": (
        "You are a receipt and workshop-invoice OCR extractor. From the receipt "
        "text extract structured line items. "
        'Return STRICT JSON: {"vendor": string|null, "invoice_date": string|null, '
        '"total": number|null, "tax": number|null, "currency": "AUD", '
        '"items": [{"kind": "part"|"labour", "name": string, '
        '"quantity": int, "unit_cost": number, "warranty_months": int|null}], '
        '"next_recommended_service": string|null, "warranty_notes": string|null}'
    ),
    "resale": (
        "You are a used-car valuation expert. Using vehicle attributes, service "
        "history count, modifications, condition and fuel efficiency, estimate "
        "resale value in AUD with a low/high range and actionable advice. "
        'Return STRICT JSON: {"estimated_value": number, "low": number, '
        '"high": number, "currency": "AUD", '
        '"factors": {string: number|string}, "recommendations": [string], '
        '"trend": []}'
    ),
    "mod-impact": (
        "You are an automotive modification analyst. Given a modification name, "
        "category, vehicle and notes, estimate performance, resale value and "
        "reliability impact. "
        'Return STRICT JSON: {"summary": string, '
        '"performance_score": number|null (0-10), '
        '"value_impact": number|null, '
        '"reliability_impact": "None"|"Minor"|"Medium"|"High", '
        '"model": "9router"}'
    ),
}


def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://your-9router-instance:port/v1").rstrip("/")


def router_enabled() -> bool:
    url = router_url()
    return bool(url) and "your-9router-instance" not in url


def router_model() -> str:
    return os.getenv("AI_ROUTER_MODEL", "General-Use")


def _clean_json(text: str) -> dict:
    """Extract the JSON object from a model response (handles fenced/wrapped JSON)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model response")
    return json.loads(text[start : end + 1])


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

    body = {
        "model": router_model(),
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPTS.get(module, "Return STRICT JSON.")},
            {"role": "user", "content": json.dumps(payload)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
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
