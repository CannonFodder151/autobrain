"""Electricity tracker routes (AUT-2436).

Same shape as the fuel router so the frontend can drop in an EV screen
without server-side changes: list/add/update/delete/stats.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.electricity import ElectricityLog
from app.models.user import User
from app.schemas.electricity import (
    ElectricityLogCreate,
    ElectricityLogOut,
    ElectricityLogUpdate,
    ElectricityStats,
)
from app.services import electricity as elec_svc
from app.services.events import add_event
from app.services.odometer import sync_odometer
from app.services.ownership import get_accessible_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/electricity", tags=["electricity"])


@router.get("", response_model=list[ElectricityLogOut])
async def list_electricity(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ElectricityLog]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ElectricityLog)
        .where(ElectricityLog.vehicle_id == vehicle_id)
        .order_by(ElectricityLog.charge_date.desc())
    )
    return list(rows)


@router.post("", response_model=ElectricityLogOut, status_code=201)
async def add_electricity(
    vehicle_id: str,
    payload: ElectricityLogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ElectricityLog:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    total = payload.total_cost if payload.total_cost else round(payload.kwh * payload.price_per_kwh, 2)
    receipt_id = await elec_svc.link_receipt(db, vehicle_id, payload.receipt_id)
    log = ElectricityLog(
        vehicle_id=vehicle_id,
        total_cost=total,
        receipt_id=receipt_id,
        **payload.model_dump(exclude={"total_cost", "receipt_id"}),
    )
    db.add(log)
    await db.flush()
    await elec_svc.recompute_efficiency(db, vehicle_id)
    await sync_odometer(db, vehicle, payload.odometer_km, elec_svc.ref_time(log))
    await add_event(
        db,
        vehicle_id,
        "charge",
        f"Charge {payload.kwh:.2f} kWh @ {payload.odometer_km:,} km",
        payload.charge_date,
        payload.odometer_km,
        total,
        log.id,
    )
    await db.commit()
    await db.refresh(log)
    return log


@router.patch("/{log_id}", response_model=ElectricityLogOut)
async def update_electricity(
    vehicle_id: str,
    log_id: str,
    payload: ElectricityLogUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ElectricityLog:
    await get_accessible_vehicle(db, vehicle_id, user)
    log = await db.get(ElectricityLog, log_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Electricity log not found")
    data = payload.model_dump(exclude_unset=True)
    if "receipt_id" in data:
        data["receipt_id"] = await elec_svc.link_receipt(db, vehicle_id, data["receipt_id"])
    if "total_cost" in data and data["total_cost"] is None:
        data.pop("total_cost")
    if data.get("total_cost") is None:
        data["total_cost"] = round(
            data.get("kwh", log.kwh) * data.get("price_per_kwh", log.price_per_kwh), 2
        )
    for key, value in data.items():
        setattr(log, key, value)
    if log.odometer_km <= 0:
        raise HTTPException(status_code=422, detail="odometer_km must be positive")
    await elec_svc.recompute_efficiency(db, vehicle_id)
    await db.flush()
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    await sync_odometer(db, vehicle, log.odometer_km, elec_svc.ref_time(log))
    await db.commit()
    await db.refresh(log)
    return log


@router.delete("/{log_id}", status_code=204)
async def delete_electricity(
    vehicle_id: str,
    log_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    log = await db.get(ElectricityLog, log_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Electricity log not found")
    await db.delete(log)
    await elec_svc.recompute_efficiency(db, vehicle_id)
    await db.commit()


@router.get("/stats", response_model=ElectricityStats)
async def electricity_stats(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ElectricityStats:
    await get_accessible_vehicle(db, vehicle_id, user)
    return await elec_svc.compute_electricity_stats(db, vehicle_id)
