"""Deterministic parts normaliser for the SCA parts-guide (AUT-1792).

The market-data scraper already returns a normalised, classified parts list.
This fallback is the deterministic formatting layer the backend runs BEFORE
asking 9Router to tidy: it canonicalises brand names (SCA house/known brands),
trims/title-cases descriptions, and guarantees every part carries a
service_group + valid category. The 9Router call (see ai/app/modules/
parts_format.py) only refines the human-readable text on top of this baseline.
"""

from __future__ import annotations

# Brand aliases -> canonical SCA-stocked brand. Keep lowercase keys.
_BRAND_CANON: dict[str, str] = {
    "castrol": "Castrol",
    "penrite": "Penrite",
    "nulon": "Nulon",
    "ryco": "Ryco",
    "bosch": "Bosch",
    "ngk": "NGK",
    "champion": "Champion",
    "bendix": "Bendix",
    "repco": "Repco",
    "sca": "SCA",
    "century": "Century",
    "narva": "Narva",
    "gates": "Gates",
    "bridgestone": "Bridgestone",
    "dunlop": "Dunlop",
    "goodyear": "Goodyear",
    "michelin": "Michelin",
}

# Allowed output keys (defence against a hallucinated router response).
_PART_KEYS = (
    "name", "sku", "category", "service_group", "service_group_key",
    "brand", "supplier", "unit_cost", "quantity", "notes",
)


def _canon_brand(brand: str | None) -> str | None:
    if not brand:
        return brand
    return _BRAND_CANON.get(brand.strip().lower(), brand.strip())


def _title(text: str | None) -> str | None:
    if not text:
        return text
    return " ".join(w.capitalize() if len(w) > 2 else w for w in str(text).split()).strip()


def format_parts_fallback(payload: dict) -> dict:
    raw = payload.get("parts") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raw = []
    parts = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        clean = {k: p.get(k) for k in _PART_KEYS if p.get(k) is not None}
        clean["brand"] = _canon_brand(clean.get("brand"))
        clean["name"] = _title(clean.get("name")) or clean.get("name")
        # Drop parts with no usable name — they can't be imported into inventory.
        if not (clean.get("name") or "").strip():
            continue
        clean["category"] = (clean.get("category") or "other").strip().lower()
        # service_group falls back to category label if the scraper omitted it.
        if not clean.get("service_group"):
            clean["service_group"] = _title(clean.get("category")) or "Other"
        if clean.get("unit_cost") is not None:
            try:
                clean["unit_cost"] = round(float(clean["unit_cost"]), 2)
            except (TypeError, ValueError):
                clean.pop("unit_cost", None)
        if clean.get("quantity") is not None:
            try:
                clean["quantity"] = int(clean["quantity"])
            except (TypeError, ValueError):
                clean.pop("quantity", None)
        parts.append(clean)
    return {
        "parts": parts,
        "model": "rule-based-fallback",
        "service_groups": sorted({p.get("service_group") for p in parts if p.get("service_group")}),
    }
