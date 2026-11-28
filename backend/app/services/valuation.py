"""Valuation service: optimized data gathering and caching."""

import asyncio
import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.mod import Modification
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle
from app.services.cache import cache_get, cache_set, _cache_key
from app.services.market_data import get_market_data

logger = get_logger(__name__)

_VALUATION_CACHE_TTL = 3600  # 1 hour
_VALUATION_CACHE_PREFIX = "valuation"


async def build_valuation_data(db: AsyncSession, vehicle: Vehicle) -> dict[str, Any]:
    """Build valuation data from vehicle and related records using concurrent queries."""
    
    # Run all queries concurrently
    services_task = db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle.id,
            ServiceRecord.status == "completed",
        )
    )
    mods_task = db.scalars(
        select(Modification).where(Modification.vehicle_id == vehicle.id)
    )
    fuel_task = db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle.id).order_by(FuelLog.fill_date)
    )
    diagnostics_task = db.scalars(
        select(Diagnostic).where(Diagnostic.vehicle_id == vehicle.id)
    )
    market_task = get_market_data(db, vehicle.make, vehicle.model, vehicle.year, vehicle.vehicle_type)
    
    services, mods, fuel, diagnostics, market = await asyncio.gather(
        services_task, mods_task, fuel_task, diagnostics_task, market_task
    )
    
    services = list(services)
    mods = list(mods)
    fuel = list(fuel)
    diagnostics = list(diagnostics)
    
    last_service_days = None
    if services:
        last_service = max(s.service_date for s in services)
        last_service_days = (date.today() - last_service).days
    
    fuel_with_consumption = [f for f in fuel if f.l_per_100km]
    fuel_avg = None
    if fuel_with_consumption:
        fuel_avg = round(
            sum(f.l_per_100km for f in fuel_with_consumption) / len(fuel_with_consumption), 2
        )
    
    return {
        "vehicle": {
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "odometer_km": vehicle.odometer_km,
            "condition": vehicle.condition,
            "vehicle_type": vehicle.vehicle_type,
        },
        "service_count": len(services),
        "total_service_cost": sum(s.cost for s in services),
        "last_service_days_ago": last_service_days,
        "diagnostics": [
            {"severity": d.severity, "status": d.status, "estimated_cost": d.estimated_cost}
            for d in diagnostics
        ],
        "mods": [{"name": m.name, "category": m.category, "cost": m.cost} for m in mods],
        "fuel_avg_l_per_100km": fuel_avg,
        "market": market,
    }


async def get_cached_valuation(vehicle_id: str) -> dict[str, Any] | None:
    """Get cached valuation result."""
    key = _cache_key(_VALUATION_CACHE_PREFIX, vehicle_id)
    cached = await cache_get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    return None


async def cache_valuation(vehicle_id: str, result: dict[str, Any]) -> None:
    """Cache valuation result."""
    key = _cache_key(_VALUATION_CACHE_PREFIX, vehicle_id)
    await cache_set(key, json.dumps(result), _VALUATION_CACHE_TTL)


async def invalidate_valuation_cache(vehicle_id: str) -> None:
    """Invalidate valuation cache for a vehicle."""
    key = _cache_key(_VALUATION_CACHE_PREFIX, vehicle_id)
    from app.services.cache import cache_delete
    await cache_delete(key)