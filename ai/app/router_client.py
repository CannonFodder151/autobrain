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
        '"parts_needed": [string], '
        '"parts": [{"name": string, "part_number": string|null}], '
        '"repair_notes": string, '
        '"estimated_cost": number|null}], '
        '"parts_needed": [string], "recommended_actions": [string]}'
        "For each part include a real-world part number when you can identify one "
        "(e.g. NGK BKR6EIX, RYCO Z89A); otherwise null."
    ),
    "service-prediction": (
        "You are an automotive maintenance scheduler. Use the manufacturer "
        "service interval for the given make/model and service type, cross-"
        "checked against the vehicle's actual service_history (a list of past "
        "completed services with service_date/odometer_km/service_type) to "
        "derive realistic intervals, plus the current odometer. "
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
        "You are a used-car valuation expert. The deterministic engine has "
        "already computed a market-anchored AUD estimate (estimated_value, low, "
        "high) — do NOT re-estimate it; those numbers are authoritative. "
        "Your job is to supply market facts plus advice: if you can identify "
        "the vehicle's new-car RRP in AUD, return it as rrp, and a realistic "
        "current used selling price on the Australian market as used_price. "
        "Given vehicle attributes, service history count, modifications, "
        "condition and fuel efficiency, add actionable advice: "
        'Return STRICT JSON: {"rrp": number|null, "used_price": number|null, '
        '"factors": {string: number|string}, '
        '"recommendations": [string], "trend": []}. '
        "Keep factors/recommendations AU-market-specific."
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
    "fuel-ocr": (
        "You are a fuel station receipt OCR extractor. From the receipt text "
        "extract the fuel purchase. "
        'Return STRICT JSON: {"vendor": string|null, "date": string|null '
        '(ISO YYYY-MM-DD), "litres": number|null, "price_per_litre": number|null, '
        '"total_cost": number|null, "currency": "AUD", "notes": string|null}'
    ),
    "odometer": (
        "You are an odometer-reading OCR engine. The user photographed a car "
        "dashboard; read the odometer value shown. "
        'Return STRICT JSON: {"odometer_km": int|null, "confidence": number (0-1)}. '
        "If the reading is not clearly visible, return odometer_km null with low confidence."
    ),
}

# Sampling temperature per module. All modules default to 0 (deterministic);
# stable resale estimates depend on this.
_TEMPERATURES: dict[str, float] = {}

# Keys the rule engines produce deterministically (measurements, identifiers,
# currency). The router may enrich the baseline but never override these —
# they are the ground truth and the whole point of deterministic-first.
_AI_IMMUTABLE: dict[str, frozenset[str]] = {
    "resale": frozenset({"estimated_value", "low", "high", "currency"}),
    "mod-impact": frozenset({"performance_score", "value_impact", "reliability_impact"}),
    "ocr": frozenset({"vendor", "invoice_date", "total", "tax", "currency", "items"}),
    "fuel-ocr": frozenset({"vendor", "date", "litres", "price_per_litre", "total_cost", "currency"}),
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
        "temperature": _TEMPERATURES.get(module, 0.0),
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
    merged = dict(baseline)
    enriched = False
    for key, value in result.items():
        if key == "model" or key in immutable:
            continue
        merged[key] = value
        enriched = True
    if enriched:
        merged["model"] = "rule-based+ai"
    return merged
