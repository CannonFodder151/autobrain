"""AI module: SCA parts-guide formatting with 9Router.

Deterministic baseline first: classify and normalise Supercheap Auto parts
categories into Inventory-shaped suggestions. 9Router then *tidies* descriptions,
brands, categories per part (never overrides the deterministic sku /
service_group / supplier, and never invents parts).

Two input shapes are accepted — exactly one:
  - ``categories``: raw SCA category taxonomy
    ({slug, name, service_group, part_category, url}) -> built via the fallback.
  - ``parts``: already-formatted Inventory parts (e.g. from the 24h cache) ->
    passed straight through so the 9Router tidy/merge is still applied.

When ``service_type`` + ``inventory`` are also supplied, the deterministic
prefill engine orders suggested parts inventory-first then SCA, and exposes
them under ``suggested_parts``.
"""

from app.fallbacks.parts_guide import (
    build_inventory_from_categories,
    suggest_parts_for_service,
)
from app.router_client import route


async def run(payload: dict) -> dict:
    categories = payload.get("categories") or []
    vehicle = payload.get("vehicle", {})
    service_type = payload.get("service_type")

    if categories:
        baseline_parts = build_inventory_from_categories(categories, vehicle)
        source = "supercheap"
    else:
        baseline_parts = list(payload.get("parts") or [])
        source = "supercheap-cached" if baseline_parts else "none"

    if not baseline_parts and not service_type:
        return {"parts": [], "vehicle": vehicle,
                "note": "no SCA categories to format"}

    result: dict = {
        "parts": baseline_parts,
        "vehicle": vehicle,
        "source": source,
        "model": "rule-based",
    }

    if service_type and baseline_parts:
        result["suggested_parts"] = suggest_parts_for_service(
            service_type, payload.get("inventory", []), baseline_parts)

    # Per-item tidy: 9Router returns the same ordered parts list; we copy only
    # the human-readable fields it is allowed to touch (description/brand/
    # category), leaving the deterministic sku/service_group/supplier intact.
    ai = await route("parts-guide", payload)
    if isinstance(ai, dict):
        ai_parts = ai.get("parts") if isinstance(ai.get("parts"), list) else None
        if ai_parts:
            for i, tidy in enumerate(ai_parts):
                if i >= len(result["parts"]) or not isinstance(tidy, dict):
                    break
                part = result["parts"][i]
                for field in ("description", "brand", "category"):
                    val = tidy.get(field)
                    if isinstance(val, str) and val.strip():
                        part[field] = val.strip()
            if ai.get("note"):
                result["note"] = ai["note"]
            result["model"] = "rule-based+ai"

    return result