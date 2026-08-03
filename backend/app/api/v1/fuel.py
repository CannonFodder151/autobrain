"""Fuel tracker routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.api.v1.vehicles import add_event, _get_owned_vehicle
from app.db.session import get_db
from app.models.fuel import FuelLog
from app.models.user import User
from app.schemas.fuel import FuelLogCreate, FuelLogOut, FuelStats

router = APIRouter(prefix="/vehicles/{vehicle_id}/fuel", tags=["fuel"])


@router.get("", response_model=list[FuelLogOut])
async def list_fuel(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FuelLog]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.fill_date.desc())
    )
    return list(rows)


@router.post("", response_model=FuelLogOut, status_code=201)
async def add_fuel(
    vehicle_id: str,
    payload: FuelLogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelLog:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    total = payload.total_cost if payload.total_cost else round(payload.litres * payload.price_per_litre, 2)
    log = FuelLog(
        vehicle_id=vehicle_id,
        total_cost=total,
        **payload.model_dump(exclude={"total_cost"}),
    )
    prev = await db.scalar(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id, FuelLog.odometer_km < payload.odometer_km)
        .order_by(FuelLog.odometer_km.desc())
    )
    if prev and payload.is_full_tank and prev.is_full_tank:
        distance = payload.odometer_km - prev.odometer_km
        if distance > 0:
            log.distance_km = distance
            log.l_per_100km = round(payload.litres / distance * 100, 2)
            log.cost_per_km = round(total / distance, 4)
    db.add(log)
    await db.flush()
    if vehicle.odometer_km is None or payload.odometer_km > vehicle.odometer_km:
        vehicle.odometer_km = payload.odometer_km
    await add_event(
        db,
        vehicle_id,
        "fuel",
        f"Fuel {payload.litres:.1f}L @ {payload.odometer_km:,} km",
        payload.fill_date,
        payload.odometer_km,
        total,
        log.id,
    )
    await db.commit()
    await db.refresh(log)
    from app.workers.tasks import check_due_notifications
    check_due_notifications.delay(vehicle_id)
    return log


@router.delete("/{fuel_id}", status_code=204)
async def delete_fuel(
    vehicle_id: str,
    fuel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_owned_vehicle(db, vehicle_id, user)
    log = await db.get(FuelLog, fuel_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Fuel log not found")
    await db.delete(log)
    await db.commit()


@router.get("/stats", response_model=FuelStats)
async def fuel_stats(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FuelStats:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = list(
        (
            await db.scalars(
                select(FuelLog)
                .where(FuelLog.vehicle_id == vehicle_id)
                .order_by(FuelLog.fill_date.asc())
            )
        ).all()
    )
    totals = await db.execute(
        select(
            func.coalesce(func.sum(FuelLog.litres), 0),
            func.coalesce(func.sum(FuelLog.total_cost), 0),
        ).where(FuelLog.vehicle_id == vehicle_id)
    )
    total_litres, total_cost = totals.one()
    eff = [r for r in rows if r.l_per_100km is not None]
    costk = [r for r in rows if r.cost_per_km is not None]
    series = [
        {
            "date": str(r.fill_date),
            "odometer": r.odometer_km,
            "l_per_100km": r.l_per_100km,
            "cost_per_km": r.cost_per_km,
            "price_per_litre": r.price_per_litre,
        }
        for r in rows
    ]
    last = rows[-1] if rows else None
    return FuelStats(
        total_litres=round(total_litres, 2),
        total_cost=round(total_cost, 2),
        avg_l_per_100km=round(sum(x.l_per_100km for x in eff) / len(eff), 2) if eff else None,
        avg_cost_per_km=round(sum(x.cost_per_km for x in costk) / len(costk), 4) if costk else None,
        last_log=FuelLogOut.model_validate(last) if last else None,
        series=series,
    )

