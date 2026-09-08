"""Supercheap Auto parts-guide lookup, formatted for AutoBrain inventory.

Orchestrates: vehicle resolution (rego+state via the rego-lookup API) →
SCA category scrape via the self-hosted market-data container → 9Router
formatting (deterministic classification + AI tidy) → Inventory-shaped JSON.

The result is cached in ``sca_parts_cache`` keyed by (make,model,year) for
24h so repeated lookups are stable and cheap, mirroring market_data.py.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.sca_parts import SCAPartsCache
from app.services import ai_client
from app.services.rego import lookup_rego

logger = get_logger(__name__)

CACHE_TTL_HOURS = 24


def _cache_key(make: str, model: str, year: int | None) -> str:
    return f"{(make or '').lower()}|{(model or '').lower()}|{year or ''}"


async def lookup_vehicle(rego: str | None, state: str | None,
                         make: str, model: str, year: int | None,
                         vehicle_type: str = "car") -> dict | None:
    """Resolve vehicle from rego+state, with deterministic rego fallback."""
    if rego and state:
        try:
            hit = await lookup_rego(rego, state=state.upper(), vehicle_type=vehicle_type)
            if hit:
                return hit
        except Exception as exc:
            logger.warning("sca_rego_lookup_failed", error=str(exc), rego=rego, state=state)
    if make or model:
        return {"make": make or None, "model": model or None, "year": year,
                "source": "user-input", "rego": rego}
    return None


async def _fetch_sca_categories(vehicle: dict) -> dict | None:
    """POST /sca-parts to the self-hosted market-data container."""
    if not settings.MARKET_DATA_URL:
        return None
    url = settings.MARKET_DATA_URL.rstrip("/") + "/sca-parts"
    payload = {
        "rego": vehicle.get("rego") or "",
        "state": vehicle.get("state") or "",
        "make": vehicle.get("make") or "",
        "model": vehicle.get("model") or "",
        "year": vehicle.get("year"),
    }
    headers = {"X-API-Key": settings.MARKET_DATA_API_KEY} if settings.MARKET_DATA_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("ok") is False:
                logger.warning("market_data_sca_degraded", note=data.get("note"))
            return data
    except Exception as exc:
        logger.warning("market_data_sca_failed", error=str(exc))
        return None


def _serialise(row: SCAPartsCache) -> dict:
    try:
        parts = json.loads(row.parts_json) if row.parts_json else []
    except (TypeError, ValueError):
        parts = []
    return {"parts": parts, "as_of": row.fetched_at.isoformat() if row.fetched_at else None, "stale": False}


def _fresh(row: SCAPartsCache) -> bool:
    fetched = row.fetched_at
    if fetched is None:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched < timedelta(hours=CACHE_TTL_HOURS)


async def _store(db: AsyncSession, key: str, data: dict) -> None:
    row = await db.scalar(select(SCAPartsCache).where(SCAPartsCache.cache_key == key))
    if row is None:
        row = SCAPartsCache(cache_key=key)
        db.add(row)
    row.parts_json = json.dumps(data.get("parts", []))
    row.category_count = len(data.get("parts", []))
    row.fetched_at = datetime.now(timezone.utc)
    await db.commit()


async def lookup_sca_parts(
    db: AsyncSession,
    rego: str | None = None,
    state: str | None = None,
    make: str = "",
    model: str = "",
    year: int | None = None,
    vehicle_type: str = "car",
    refresh: bool = False,
) -> dict:
    """Resolve the vehicle, scrape SCA categories, format via the AI gateway.

    Returns Inventory-shaped parts: {parts: [...], vehicle, source, model, note}.
    Always returns a dict (never raises); degrades deterministically when any
    upstream — 9Router, market-data, rego — is unavailable.
    """
    vehicle = await lookup_vehicle(
        rego, state, make, model, year, vehicle_type)
    make_l = (vehicle.get("make") or "").strip().lower()
    model_l = (vehicle.get("model") or "").strip().lower()
    year_val = vehicle.get("year")

    key = _cache_key(make_l, model_l, year_val)
    if not refresh:
        row = await db.scalar(select(SCAPartsCache).where(SCAPartsCache.cache_key == key))
        if row is not None and _fresh(row):
            return {**_serialise(row), "vehicle": vehicle, "cache": True}

    raw = await _fetch_sca_categories(vehicle) or {}
    categories = raw.get("categories", []) if isinstance(raw, dict) else []
    payload = {"vehicle": vehicle, "categories": categories}
    if not categories:
        payload["note"] = raw.get("note") or "SCA parts-guide unavailable"

    formatted = await ai_client.format_sca_parts(payload)
    data = {
        "parts": formatted.get("parts", []) if formatted else [],
        "vehicle": vehicle,
        "source": "sca+9router",
        "model": formatted.get("model", "rule-based") if formatted else "rule-based",
        "note": formatted.get("note") if formatted else (payload.get("note")),
    }
    await _store(db, key, data)
    return {**data, "cache": False}


async def suggest_service_parts(
    db: AsyncSession,
    vehicle_id: str,
    make: str, model: str, year: int,
    service_type: str,
    rego: str | None = None,
    state: str | None = None,
    vehicle_type: str = "car",
    refresh: bool = False,
) -> dict:
    """Prefill parts for an AI-suggested service: inventory FIRST, then SCA.

    Returns {service_type, items: [ServiceItemIn-like dicts]}.
    """
    from app.models.part import Part
    rows = await db.scalars(select(Part).where(Part.vehicle_id == vehicle_id))
    inventory_parts = [{
        "name": r.name,
        "category": r.category,
        "quantity": r.quantity,
        "min_quantity": r.min_quantity,
        "unit_cost": float(r.unit_cost or 0),
        "sku": r.sku,
        "id": r.id,
        "source": "inventory",
    } for r in rows]

    sca = await lookup_sca_parts(
        db, rego=rego, state=state, make=make, model=model, year=year,
        vehicle_type=vehicle_type, refresh=refresh)
    sca_parts = sca.get("parts", [])

    # Ask the AI gateway to run the preference-ordered suggestion, then return
    # ServiceItemIn-shaped dicts (quantity defaults to 1 for suggested parts).
    suggestion = await ai_client.format_sca_parts({
        "vehicle": sca.get("vehicle", {}),
        "parts": sca_parts,
        "service_type": service_type,
        "inventory": inventory_parts,
    })
    items = []
    if suggestion and isinstance(suggestion.get("suggested_parts"), list):
        for sp in suggestion["suggested_parts"]:
            items.append({
                "part_id": sp.get("id"),
                "name": sp.get("name") or "",
                "quantity": 1,
                "unit_cost": float(sp.get("unit_cost", 0) or 0),
                "kind": "part",
                "part_no": sp.get("sku"),
            })
    if not items:
        for sp in sca_parts[:6]:
            items.append({
                "name": sp.get("name") or "",
                "quantity": 1,
                "unit_cost": 0.0,
                "kind": "part",
                "part_no": sp.get("sku"),
            })
    return {"service_type": service_type, "items": items,
            "inventory_count": len(inventory_parts),
            "sca_count": len(sca_parts)}


async def clear_sca_cache(db: AsyncSession, make: str, model: str, year: int | None) -> None:
    await db.execute(delete(SCAPartsCache).where(
        SCAPartsCache.cache_key == _cache_key(make, model, year)))
    await db.commit()


async def list_vehicle_signatures(db: AsyncSession) -> list[dict]:
    """Return distinct (make, model, year) tuples from the vehicles table.

    Used by the nightly prewarm task — empty fields are dropped so we only
    request meaningful SCA lookups. Capped at 1000 to keep the daily run
    bounded (the fleet is in the low hundreds today).
    """
    from app.models.vehicle import Vehicle

    rows = (await db.execute(
        select(
            Vehicle.make, Vehicle.model, Vehicle.year, func.count(Vehicle.id)
        )
        .where(Vehicle.make.isnot(None), Vehicle.model.isnot(None))
        .group_by(Vehicle.make, Vehicle.model, Vehicle.year)
        .limit(1000)
    )).all()
    return [
        {"make": m, "model": md, "year": y, "vehicle_count": int(c)}
        for m, md, y, c in rows
    ]