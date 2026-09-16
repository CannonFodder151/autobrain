"""Vehicle health score routes.

Determines a single 0–100 health score from diagnostics, maintenance,
fuel efficiency, OBD codes and parts wear.  The deterministic rule engine
runs first (in the AI gateway's fallback); this route assembles the input
payload and caches the result on the vehicle_health_scores table.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.obd import ObdCode
from app.models.part import Part
from app.models.service import ServiceRecord
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_health_score import VehicleHealthScore
from app.schemas.vehicle_health_score import VehicleHealthScoreOut
from app.services.ai_client import compute_health_score
from app.services.ownership import get_accessible_vehicle

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles/{vehicle_id}/health-score", tags=["health-score"])


@router.get("", response_model=VehicleHealthScoreOut)
async def get_health_score(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VehicleHealthScoreOut:
    """Compute (or return cached) health score for the vehicle.

    Deterministic rule engine assembles the payload; 9Router enriches with
    narrative / extra alerts when reachable.  Returns the cached score if
    computed within the last 24h (unless ``force=true``).
    """
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    # Check cache (24h freshness)
    cached = await db.scalar(
        select(VehicleHealthScore).where(VehicleHealthScore.vehicle_id == vehicle_id)
    )
    # Always recompute — the score depends on mutable data; caching strategy
    # is a future optimisation (AUT-3359).  For now, every request is fresh.
    # ponytail: cache with 24h TTL when read volume justifies it.

    payload = await _build_health_payload(db, vehicle_id, vehicle)
    result = await compute_health_score(payload)
    if not result:
        result = {"score": 0, "status_label": "unknown", "breakdown": {}, "alerts": [], "model": "fallback"}

    response = VehicleHealthScoreOut(
        vehicle_id=vehicle_id,
        nickname=vehicle.nickname,
        score=result.get("score", 0),
        status_label=result.get("status_label", "unknown"),
        breakdown=result.get("breakdown", {}),
        last_computed=datetime.utcnow().isoformat(),
        computed_by=result.get("model", "deterministic"),
    )

    # Upsert the cached score
    if cached:
        cached.score = response.score
        cached.last_computed = datetime.utcnow()
        cached.computed_by = response.computed_by
    else:
        db.add(VehicleHealthScore(
            vehicle_id=vehicle_id,
            score=response.score,
            computed_by=response.computed_by,
            notes=result.get("summary"),
        ))
    await db.commit()

    logger.info("health_score_computed", vehicle_id=vehicle_id, score=response.score, computed_by=response.computed_by)
    return response


@router.get("/alerts", response_model=list[dict])
async def get_health_alerts(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Predictive failure alerts for the vehicle (computed from latest data)."""
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    payload = await _build_health_payload(db, vehicle_id, vehicle)
    result = await compute_health_score(payload)
    if not result:
        return []
    return result.get("alerts", [])


async def _build_health_payload(db: AsyncSession, vehicle_id: str, vehicle: Vehicle) -> dict:
    """Assemble the data payload consumed by the AI gateway health-score module."""
    # Open diagnostics
    diagnostics = list((await db.scalars(
        select(Diagnostic).where(
            Diagnostic.vehicle_id == vehicle_id, Diagnostic.status == "open"
        )
    )).all())

    # Open OBD codes
    obd_codes = list((await db.scalars(
        select(ObdCode).where(
            ObdCode.vehicle_id == vehicle_id, ObdCode.is_resolved == False
        )
    )).all())

    # Completed services
    service_records = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id, ServiceRecord.status == "completed"
        )
    )).all())
    completed_services = len(service_records)

    # Scheduled services
    scheduled = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id, ServiceRecord.status == "scheduled"
        )
    )).all())
    has_scheduled = len(scheduled) > 0

    # Months since last service
    months_since_last = 0.0
    if service_records:
        last_service = max(service_records, key=lambda s: s.service_date)
        from datetime import date as d
        today = d.today()
        months_since_last = (today - last_service.service_date).days / 30.0

    # Fuel efficiency
    fuel_logs = list((await db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.fill_date)
    )).all())
    effs = [f.l_per_100km for f in fuel_logs if f.l_per_100km is not None]
    avg_fuel = sum(effs) / len(effs) if effs else None

    # Parts inventory
    parts = list((await db.scalars(
        select(Part).where(Part.vehicle_id == vehicle_id)
    )).all())

    # Vehicle age
    vehicle_age_years = None
    if vehicle.year:
        from datetime import date as d
        vehicle_age_years = d.today().year - vehicle.year

    return {
        "diagnostics": [
            {"severity": d.severity, "summary": d.summary}
            for d in diagnostics
        ],
        "obd_codes": [
            {"code": c.code, "description": c.description}
            for c in obd_codes
        ],
        "completed_services": completed_services,
        "has_scheduled": has_scheduled,
        "months_since_last_service": round(months_since_last, 1),
        "avg_fuel_efficiency": round(avg_fuel, 2) if avg_fuel else None,
        "parts": [
            {"name": p.name, "quantity": p.quantity, "min_quantity": p.min_quantity}
            for p in parts
        ],
        "vehicle_age_years": vehicle_age_years,
        "vehicle": {
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "odometer_km": vehicle.odometer_km,
            "condition": vehicle.condition,
        },
    }