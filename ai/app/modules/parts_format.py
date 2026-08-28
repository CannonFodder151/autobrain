"""AI module: parts formatting (AUT-1792).

Tidies SCA parts-guide output — descriptions, brands, categories — via 9Router.
Deterministic-first: the rule engine (app.fallbacks.parts_format) canonicalises
brands/categories and guarantees a service_group. 9Router then refines the
human-readable text; its response is re-validated against the allowed part keys
before it can replace the deterministic baseline, so a junk response can never
inject fields the inventory tab doesn't understand.
"""

from app.fallbacks.parts_format import format_parts_fallback, _PART_KEYS
from app.router_client import route


def _clean_part(p: dict) -> dict:
    if not isinstance(p, dict):
        return {}
    out = {}
    for k in _PART_KEYS:
        v = p.get(k)
        if v is None:
            continue
        if k in ("unit_cost",):
            try:
                out[k] = round(float(v), 2)
            except (TypeError, ValueError):
                pass
        elif k in ("quantity",):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
        else:
            out[k] = str(v)
    return out


async def run(payload: dict) -> dict:
    baseline = format_parts_fallback(payload)
    result = await route("parts-format", payload)
    if isinstance(result, dict) and isinstance(result.get("parts"), list):
        tidied = [_clean_part(p) for p in result["parts"]]
        tidied = [p for p in tidied if p.get("name")]
        if tidied:
            return {
                "parts": tidied,
                "model": "rule-based+ai",
                "service_groups": sorted({p.get("service_group") for p in tidied if p.get("service_group")}),
            }
    return baseline
