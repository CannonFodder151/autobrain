"""Resale value estimation routes."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_ai
from app.api.v1.vehicles import _get_owned_vehicle
from app.db.session import get_db
from app.models.fuel import FuelLog
from app.models.mod import Modification
from app.models.service import ServiceRecord
from app.models.user import User
from app.models.valuation import ValuationSnapshot
from app.schemas.valuation import ValuationOut, ValuationRequest, ValuationResponse
from app.services.ai_client import estimate_value

router = APIRouter(prefix="/vehicles/{vehicle_id}/valuation", tags=["valuation"])


@router.post("", response_model=ValuationResponse)
async def valuate(
    vehicle_id: str,
    payload: ValuationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_ai),
) -> ValuationResponse:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    services = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",
        )
    )).all())
    mods = list((await db.scalars(
        select(Modification).where(Modification.vehicle_id == vehicle_id)
    )).all())
    fuel = list((await db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle_id).order_by(FuelLog.fill_date)
    )).all())
    data = {
        "vehicle": {
            "make": vehicle.make, "model": vehicle.model, "year": vehicle.year,
            "engine": vehicle.engine, "odometer_km": payload.odometer_km or vehicle.odometer_km,
            "condition": payload.condition or vehicle.condition,
        },
        "service_count": len(services),
        "total_service_cost": sum(s.cost for s in services),
        "mods": [{"name": m.name, "category": m.category, "cost": m.cost} for m in mods],
        "fuel_avg_l_per_100km": (
            round(sum(f.l_per_100km for f in fuel if f.l_per_100km) / sum(1 for f in fuel if f.l_per_100km), 2)
            if any(f.l_per_100km for f in fuel) else None
        ),
        **((payload.extra_context or {})),
    }
    result = await estimate_value(data)
    if not result:
        raise HTTPException(status_code=503, detail="Valuation engine unavailable")
    snapshot = ValuationSnapshot(
        vehicle_id=vehicle_id,
        estimated_value=result["estimated_value"],
        low=result["low"],
        high=result["high"],
        currency=result.get("currency", "AUD"),
        factors=json.dumps(result.get("factors", {})),
        recommendations=json.dumps(result.get("recommendations", [])),
    )
    db.add(snapshot)
    await db.commit()
    history = list((await db.scalars(
        select(ValuationSnapshot).where(ValuationSnapshot.vehicle_id == vehicle_id)
    )).all())
    result["trend"] = [
        {"date": str(s.created_at.date()), "value": s.estimated_value}
        for s in history
    ]
    return ValuationResponse(**result)


@router.get("/history", response_model=list[ValuationOut])
async def valuation_history(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ValuationSnapshot]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.vehicle_id == vehicle_id)
        .order_by(ValuationSnapshot.created_at.desc())
    )
    return list(rows)

