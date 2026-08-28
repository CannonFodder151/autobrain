"""Supercheap Auto parts-guide integration for the inventory tab (AUT-1792).

Calls the self-hosted market-data API's ``/parts-guide`` (X-API-Key, same
pattern as rego/valuation), then runs the result through the AI formatting
layer (9Router parts-format, deterministic-first) to tidy descriptions, brands
and categories. Returns Inventory-formatted JSON the inventory tab imports.

Deterministic-first: the market-data scraper always returns a canonical
service-parts catalogue, so the feature works with no live SCA access. When
the provider is unconfigured or fails, a clean deterministic fallback (built
from the vehicle's known attributes) is returned so the inventory tab never
errors — never a 500.
"""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.part import Part
from app.models.vehicle import Vehicle

logger = get_logger(__name__)

# service_type -> the parts categories (snake_case) that service typically needs.
# Used to prefill an AI-suggested service: inventory parts first, then SCA.
_SERVICE_PART_CATEGORIES: dict[str, list[str]] = {
    "scheduled": ["engine_oil", "oil_filter", "air_filter", "cabin_filter",
                  "wiper_blades", "battery"],
    "air_filter": ["air_filter", "cabin_filter"],
    "brake_fluid": ["brake_fluid"],
    "coolant": ["coolant"],
    "spark_plugs": ["spark_plugs", "ignition_leads", "glow_plugs"],
    "brake_pads": ["brake_pads_front", "brake_pads_rear", "brake_fluid"],
    "battery": ["battery"],
    "tyre_rotation": ["tyre"],
    "transmission": ["transmission_fluid"],
    "timing_belt": ["drive_belt"],
}


async def _fetch_provider(rego: str, state: str, make: str, model: str,
                          year: int | None, engine: str) -> dict | None:
    if not settings.MARKET_DATA_URL:
        return None
    url = settings.MARKET_DATA_URL.rstrip("/") + "/parts-guide"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                json={"rego": rego, "state": state, "make": make,
                      "model": model, "year": year, "engine": engine},
                headers={"X-API-Key": settings.MARKET_DATA_API_KEY} if settings.MARKET_DATA_API_KEY else {},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("sca_provider_failed_falling_back", error=str(exc), rego=rego)
        return None


async def get_sca_parts_guide(
    db: AsyncSession,
    vehicle_id: str,
    rego: str = "",
    state: str = "VIC",
    make: str = "",
    model: str = "",
    year: int | None = None,
    engine: str = "",
) -> dict:
    """SCA parts-guide for a vehicle, AI-formatted, as Inventory JSON.

    Resolves make/model/year/engine from the stored vehicle when not supplied
    (e.g. the user only provides a rego). Always returns a dict the inventory
    tab can render: ``{source, mode, vehicle, categories, parts, note}``.
    """
    if not make and not rego:
        vehicle = await db.get(Vehicle, vehicle_id)
        if vehicle:
            make = make or vehicle.make or ""
            model = model or vehicle.model or ""
            year = year or vehicle.year
            engine = engine or (vehicle.engine or "")
            rego = rego or (vehicle.rego or "")
            state = state or (vehicle.state or "VIC")

    provider = await _fetch_provider(rego, state, make, model, year, engine)
    if provider and provider.get("parts"):
        guide = provider
        guide["source"] = "supercheap"
    else:
        # market-data unreachable: degrade cleanly (no duplication of the
        # catalogue — that lives in the scraper). Valuations do the same.
        guide = {
            "source": "fallback",
            "mode": "unavailable",
            "vehicle": {"rego": rego, "state": state, "make": make,
                        "model": model, "year": year, "engine": engine},
            "categories": [],
            "parts": [],
            "note": "SCA parts-guide unavailable (market-data service unreachable).",
        }

    # AI formatting layer (9Router). Always returns a dict; rules-first, so a
    # down router just hands back the deterministic baseline.
    formatted = await format_parts_safe(guide)
    return formatted


async def format_parts_safe(guide: dict) -> dict:
    """Run the parts list through the 9Router formatting layer safely."""
    from app.services.ai_client import format_parts

    payload = {"parts": guide.get("parts", []), "vehicle": guide.get("vehicle", {})}
    result = await format_parts(payload)
    if not isinstance(result, dict) or not result.get("parts"):
        # Router down / declined: keep the deterministic baseline as-is.
        return {
            "source": guide.get("source"),
            "mode": guide.get("mode", "deterministic"),
            "vehicle": guide.get("vehicle", {}),
            "categories": guide.get("categories", []),
            "parts": guide.get("parts", []),
            "service_groups": sorted({c.get("service_group") for c in guide.get("categories", [])
                                     if isinstance(c, dict) and c.get("service_group")}),
            "note": guide.get("note"),
            "formatted_with": "rule-based",
        }
    return {
        "source": guide.get("source"),
        "mode": guide.get("mode", "deterministic"),
        "vehicle": guide.get("vehicle", {}),
        "categories": guide.get("categories", []),
        "parts": result["parts"],
        "service_groups": result.get("service_groups", []),
        "note": guide.get("note"),
        "formatted_with": result.get("model", "rule-based+ai"),
    }


async def suggest_service_parts(db: AsyncSession, vehicle: Vehicle, service_type: str) -> list[dict]:
    """Prefill the parts for an AI-suggested service (AUT-1792).

    Deterministic-first and cost-aware: prefer parts already in the vehicle's
    inventory that belong to the service's categories, then fall back to the
    SCA parts-guide for any category not already stocked. Returns a list of
    ``SuggestedPart``-shaped dicts with ``source`` = inventory | sca.
    """
    categories = _SERVICE_PART_CATEGORIES.get(service_type, _SERVICE_PART_CATEGORIES["scheduled"])

    # 1) Inventory first.
    rows = await db.scalars(
        select(Part).where(Part.vehicle_id == vehicle.id, Part.category.in_(categories))
    )
    inventory = {p.category: p for p in rows}
    suggestions: list[dict] = []
    covered = set()
    for cat in categories:
        if cat in inventory:
            p = inventory[cat]
            suggestions.append({
                "name": p.name, "category": p.category,
                "service_group": None, "brand": None,
                "supplier": p.supplier, "unit_cost": p.unit_cost,
                "quantity": p.min_quantity or 1, "source": "inventory",
                "notes": p.notes,
            })
            covered.add(cat)

    # 2) SCA secondary: any service category not already in inventory.
    missing = [c for c in categories if c not in covered]
    if missing:
        guide = await get_sca_parts_guide(db, vehicle.id, make=vehicle.make or "",
                                           model=vehicle.model or "", year=vehicle.year,
                                           engine=vehicle.engine or "")
        for part in guide.get("parts", []):
            cat = part.get("category")
            if cat in missing and cat not in covered:
                suggestions.append({
                    "name": part.get("name"), "category": cat,
                    "service_group": part.get("service_group"),
                    "brand": part.get("brand"),
                    "supplier": part.get("supplier"),
                    "unit_cost": part.get("unit_cost"),
                    "quantity": part.get("quantity", 1), "source": "sca",
                    "notes": part.get("notes"),
                })
                covered.add(cat)
    return suggestions
