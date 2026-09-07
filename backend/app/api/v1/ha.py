"""Home Assistant integration routes (AUT-2541).

Mount point: ``/api/v1/ha``. The router prefix is ``/ha``; routes below are
relative to it so the final URLs resolve under ``/api/v1/ha/...``. HA's `rest`
platform is happy reading those directly.

Endpoints
---------
User-scoped (Bearer JWT):
  POST   /api/v1/ha/tokens         create a new HA token
  GET    /api/v1/ha/tokens         list the user's HA tokens
  DELETE /api/v1/ha/tokens/{id}    revoke a token

HA-scoped (X-HA-API-Key, read-only):
  GET  /api/v1/ha/vehicles                       all accessible vehicles
  GET  /api/v1/ha/vehicles/{id}/service-intervals upcoming service intervals
  GET  /api/v1/ha/vehicles/{id}/analytics        analytics summary
  GET  /api/v1/ha/service-reminders              reminders across all accessible vehicles
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_ha_user
from app.db.session import get_db
from app.models.ha import HaIntegration
from app.models.user import User
from app.schemas.ha import (
    HaAnalyticsOut,
    HaServiceIntervalOut,
    HaServiceReminderOut,
    HaTokenCreate,
    HaTokenCreated,
    HaTokenOut,
    HaVehicleOut,
)
from app.services.ha_keys import generate_key, hash_key, key_prefix
from app.services.ownership import get_accessible_vehicle

router = APIRouter(prefix="/ha", tags=["home-assistant"])


# ── user-managed tokens (Bearer auth) ────────────────────────────

@router.get("/tokens", response_model=list[HaTokenOut])
async def list_tokens(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[HaIntegration]:
    rows = await db.scalars(
        select(HaIntegration).where(HaIntegration.user_id == user.id).order_by(HaIntegration.created_at.desc())
    )
    return list(rows)


@router.post("/tokens", response_model=HaTokenCreated, status_code=201)
async def create_token(
    payload: HaTokenCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HaTokenCreated:
    raw = generate_key()
    integration = HaIntegration(
        user_id=user.id,
        label="Home Assistant",
        api_key_prefix=key_prefix(raw),
        api_key_hash=hash_key(raw),
        vehicle_id=payload.vehicle_id,
    )
    if payload.vehicle_id:
        try:
            await get_accessible_vehicle(db, payload.vehicle_id, user)
        except HTTPException:
            pass
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return HaTokenCreated.model_validate(integration.__dict__ | {"api_key": raw})


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    token = await db.get(HaIntegration, token_id)
    if not token or token.user_id != user.id:
        raise HTTPException(status_code=404, detail="Token not found")
    await db.delete(token)
    await db.commit()


# ── HA-polled endpoints (X-HA-API-Key) ──────────────────────────

@router.get("/vehicles", response_model=list[HaVehicleOut])
async def ha_vehicles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_ha_user),
) -> list[HaVehicleOut]:
    from app.services.vehicle import list_user_vehicles

    vehicles = await list_user_vehicles(db, user)
    return [
        HaVehicleOut(
            id=str(v.id),
            nickname=v.nickname,
            rego=v.rego,
            make=v.make,
            model=v.model,
            year=v.year,
            odometer_km=v.odometer_km,
            fuel_type=v.fuel_type,
            powertrain=v.powertrain,
        )
        for v in vehicles
    ]


@router.get("/vehicles/{vehicle_id}/service-intervals", response_model=list[HaServiceIntervalOut])
async def ha_service_intervals(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_ha_user),
) -> list[HaServiceIntervalOut]:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    from app.models.service import ServiceRecord

    records = list((await db.scalars(
        select(ServiceRecord)
        .where(ServiceRecord.vehicle_id == vehicle.id)
        .where(ServiceRecord.next_due_km.isnot(None) | ServiceRecord.next_due_date.isnot(None))
        .order_by(ServiceRecord.next_due_date.is_(None), ServiceRecord.next_due_date.asc())
    )).all())
    return [
        HaServiceIntervalOut(
            id=str(r.id),
            vehicle_nickname=vehicle.nickname,
            service_type=r.service_type,
            next_due_km=r.next_due_km,
            next_due_date=r.next_due_date.isoformat() if r.next_due_date else None,
            status=r.status,
        )
        for r in records
    ]


@router.get("/vehicles/{vehicle_id}/analytics", response_model=HaAnalyticsOut)
async def ha_vehicle_analytics(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_ha_user),
) -> HaAnalyticsOut:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    from app.models.fuel import FuelLog
    from app.models.mod import Modification
    from app.models.service import ServiceRecord

    fuel = list((await db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle_id).order_by(FuelLog.fill_date)
    )).all())
    services = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",
        )
    )).all())
    mods = list((await db.scalars(
        select(Modification).where(Modification.vehicle_id == vehicle_id)
    )).all())
    fuel_total = sum(f.total_cost for f in fuel)
    service_total = sum(s.cost for s in services)
    mod_total = sum(m.cost for m in mods)
    tco = fuel_total + service_total + mod_total
    total_km = 0.0
    if len(fuel) >= 2:
        total_km = max(fuel[-1].odometer_km - fuel[0].odometer_km, 0)
    cost_per_km = round(tco / total_km, 4) if total_km > 0 else None
    return HaAnalyticsOut(
        vehicle_id=vehicle.id,
        vehicle_nickname=vehicle.nickname,
        fuel_total=round(fuel_total, 2),
        service_total=round(service_total, 2),
        total_cost_of_ownership=round(tco, 2),
        cost_per_km=cost_per_km,
        total_km_tracked=round(total_km, 1),
        count_services=len(services),
    )


@router.get("/service-reminders", response_model=list[HaServiceReminderOut])
async def ha_service_reminders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_ha_user),
) -> list[HaServiceReminderOut]:
    from app.services.vehicle import list_user_vehicles
    from app.models.service import ServiceRecord

    vehicles = await list_user_vehicles(db, user)
    reminders: list[HaServiceReminderOut] = []
    for v in vehicles:
        current_odo = v.odometer_km or 0
        rows = list((await db.scalars(
            select(ServiceRecord)
            .where(
                ServiceRecord.vehicle_id == v.id,
                ServiceRecord.status == "completed",
                ServiceRecord.next_due_km.isnot(None) | ServiceRecord.next_due_date.isnot(None),
            )
            .order_by(ServiceRecord.next_due_date.is_(None), ServiceRecord.next_due_date.asc())
        )).all())
        for r in rows:
            due_in_km = None
            if r.next_due_km is not None:
                due_in_km = max(r.next_due_km - current_odo, 0)
            days_until_due = None
            if r.next_due_date is not None:
                delta = (r.next_due_date - datetime.now(timezone.utc).date()).days
                days_until_due = max(delta, 0)
            reminders.append(
                HaServiceReminderOut(
                    vehicle_id=v.id,
                    vehicle_nickname=v.nickname,
                    service_type=r.service_type,
                    next_due_km=r.next_due_km,
                    next_due_date=r.next_due_date.isoformat() if r.next_due_date else None,
                    due_in_km=due_in_km,
                    days_until_due=days_until_due,
                )
            )
    return reminders
