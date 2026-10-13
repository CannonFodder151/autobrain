"""Vehicle Health Score service.

Aggregates data from diagnostics, service records, fuel logs, OBD codes, and
parts inventory to compute a unified health score (0-100) with predictive
failure alerts. Uses the AI gateway (deterministic-first) for scoring.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.obd import ObdCode
from app.models.part import Part
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle
from app.services.ai_client import run_health_score


async def _get_diagnostics(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """Fetch recent diagnostics (last 90 days) for a vehicle."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    rows = await db.scalars(
        select(Diagnostic)
        .where(
            Diagnostic.vehicle_id == vehicle_id,
            Diagnostic.created_at >= cutoff,
        )
        .order_by(Diagnostic.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id": d.id,
            "symptoms": d.symptoms,
            "severity": d.severity,
            "status": d.status,
            "estimated_cost": d.estimated_cost,
            "created_at": d.created_at,
        }
        for d in rows
    ]


async def _get_services(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """Fetch completed service records for a vehicle."""
    rows = await db.scalars(
        select(ServiceRecord)
        .where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",
        )
        .order_by(ServiceRecord.service_date.desc())
        .limit(50)
    )
    return [
        {
            "id": s.id,
            "service_type": s.service_type,
            "service_date": s.service_date,
            "odometer_km": s.odometer_km,
            "cost": s.cost,
            "status": s.status,
        }
        for s in rows
    ]


async def _get_fuel_logs(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """Fetch fuel logs for a vehicle."""
    rows = await db.scalars(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.fill_date.desc())
        .limit(100)
    )
    return [
        {
            "id": f.id,
            "fill_date": f.fill_date,
            "odometer_km": f.odometer_km,
            "litres": f.litres,
            "l_per_100km": f.l_per_100km,
            "is_full_tank": f.is_full_tank,
        }
        for f in rows
    ]


async def _get_obd_codes(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """Fetch OBD codes for a vehicle."""
    rows = await db.scalars(
        select(ObdCode)
        .where(ObdCode.vehicle_id == vehicle_id)
        .order_by(ObdCode.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": c.id,
            "code": c.code,
            "description": c.description,
            "is_resolved": c.is_resolved,
            "created_at": c.created_at,
        }
        for c in rows
    ]


async def _get_parts(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """Fetch parts inventory for a vehicle."""
    rows = await db.scalars(
        select(Part)
        .where(Part.vehicle_id == vehicle_id)
        .order_by(Part.name)
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "quantity": p.quantity,
            "min_quantity": p.min_quantity,
            "warranty_months": p.warranty_months,
            "created_at": p.created_at,
        }
        for p in rows
    ]


async def compute_health_score(
    db: AsyncSession,
    vehicle: Vehicle,
) -> dict:
    """Compute Vehicle Health Score for a vehicle.

    Returns a dict with score (0-100), label, confidence, breakdown, alerts,
    and signals. Falls back to deterministic scoring if AI gateway unavailable.
    """
    vehicle_id = vehicle.id

    diagnostics = await _get_diagnostics(db, vehicle_id)
    services = await _get_services(db, vehicle_id)
    fuel_logs = await _get_fuel_logs(db, vehicle_id)
    obd_codes = await _get_obd_codes(db, vehicle_id)
    parts = await _get_parts(db, vehicle_id)

    payload = {
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "odometer_km": vehicle.odometer_km,
            "vehicle_type": vehicle.vehicle_type,
        },
        "diagnostics": diagnostics,
        "services": services,
        "fuel_logs": fuel_logs,
        "obd_codes": obd_codes,
        "parts": parts,
    }

    result = await run_health_score(payload)
    if not isinstance(result, dict):
        # AI gateway returned nothing — use deterministic fallback directly
        from ai.app.fallbacks.health_score import health_score_fallback
        result = health_score_fallback(
            payload["vehicle"],
            diagnostics,
            services,
            fuel_logs,
            obd_codes,
            parts,
        )

    return result