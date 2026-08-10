"""Resale value estimation routes."""

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.ownership import get_accessible_vehicle
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
    user: User = Depends(get_current_user),
) -> ValuationResponse:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    # Demo accounts get a realistic sample valuation instead of an AI call.
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Valuation is an AI feature and is disabled on the free plan. Upgrade to enable it.",
        )

    if user.role == "demo":
        today = date.today()
        return ValuationResponse(
            estimated_value=24500.0,
            low=21800.0,
            high=27900.0,
            currency="AUD",
            factors={
                "base_value": 28000.0,
                "odometer_adjustment": -3200.0,
                "condition_adjustment": 900.0,
                "mods_adjustment": 1300.0,
                "service_history_adjustment": -1500.0,
                "notes": "Sample valuation shown on the demo account. "
                         "The AI valuation engine runs on real accounts.",
            },
            recommendations=[
                "Recent full service history adds confidence to the estimate.",
                "Addressing the worn brake pads would lift the value slightly.",
                "Maintain the service log — buyers pay more for documented cars.",
            ],
            trend=[
                {"date": str(today - timedelta(days=2 * 365)), "value": 21000.0},
                {"date": str(today - timedelta(days=365)), "value": 22500.0},
                {"date": str(today), "value": 24500.0},
            ],
            model="demo-sample",
        )

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
            "vehicle_type": vehicle.vehicle_type,
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
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.vehicle_id == vehicle_id)
        .order_by(ValuationSnapshot.created_at.desc())
    )
    return list(rows)

