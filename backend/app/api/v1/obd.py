"""OBD-II routes.

Fault codes captured from a Bluetooth OBD2 adapter can be saved here and
pushed into the existing diagnostic AI tool. OBD access is admin-granted per
account; a VIN read from the adapter backfills the vehicle if missing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.api.v1.vehicles import _get_accessible_vehicle
from app.db.session import get_db
from app.models.obd import ObdCode
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.obd import (
    ObdCodeCreate,
    ObdCodeOut,
    ObdCodeUpdate,
    ObdSettingsOut,
    ObdVinRequest,
)
from app.schemas.vehicle import VehicleOut

router = APIRouter(prefix="/vehicles/{vehicle_id}/obd", tags=["obd"])


def _require_obd(user: User, vehicle: Vehicle) -> None:
    if not user.obd_enabled:
        raise HTTPException(
            status_code=403,
            detail="OBD access is not enabled for this account. Contact your administrator.",
        )


@router.get("/settings", response_model=ObdSettingsOut)
async def obd_settings(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ObdSettingsOut:
    await _get_accessible_vehicle(db, vehicle_id, user)
    return ObdSettingsOut(enabled=user.obd_enabled, auto_connect=user.obd_auto_connect)


@router.post("/vin", response_model=VehicleOut)
async def set_obd_vin(
    vehicle_id: str,
    payload: ObdVinRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    vehicle = await _get_accessible_vehicle(db, vehicle_id, user)
    _require_obd(user, vehicle)
    if vehicle.vin and len(vehicle.vin) >= 5:
        raise HTTPException(status_code=409, detail="Vehicle already has a VIN")
    vehicle.vin = payload.vin
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("/codes", response_model=list[ObdCodeOut])
async def list_codes(
    vehicle_id: str,
    q: str | None = Query(default=None, max_length=16),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ObdCode]:
    await _get_accessible_vehicle(db, vehicle_id, user)
    stmt = select(ObdCode).where(ObdCode.vehicle_id == vehicle_id)
    if q:
        stmt = stmt.where(ObdCode.code.ilike(f"%{q.upper()}%"))
    stmt = stmt.order_by(ObdCode.created_at.desc())
    return list((await db.scalars(stmt)).all())


@router.post("/codes", response_model=ObdCodeOut, status_code=201)
async def add_code(
    vehicle_id: str,
    payload: ObdCodeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ObdCode:
    vehicle = await _get_accessible_vehicle(db, vehicle_id, user)
    _require_obd(user, vehicle)
    code = ObdCode(vehicle_id=vehicle_id, code=payload.code.upper(), **payload.model_dump(exclude={"code"}))
    db.add(code)
    await db.commit()
    await db.refresh(code)
    return code


@router.patch("/codes/{code_id}", response_model=ObdCodeOut)
async def update_code(
    vehicle_id: str,
    code_id: str,
    payload: ObdCodeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ObdCode:
    await _get_accessible_vehicle(db, vehicle_id, user)
    code = await db.get(ObdCode, code_id)
    if not code or code.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="OBD code not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(code, key, value)
    await db.commit()
    await db.refresh(code)
    return code


@router.delete("/codes/{code_id}", status_code=204)
async def delete_code(
    vehicle_id: str,
    code_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_accessible_vehicle(db, vehicle_id, user)
    code = await db.get(ObdCode, code_id)
    if not code or code.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="OBD code not found")
    await db.delete(code)
    await db.commit()