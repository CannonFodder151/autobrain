"""Vehicle API router.

Thin HTTP layer over the VehicleService. Mounts under ``/vehicles``.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from .services import VehicleService
from .schemas import (
    RegoLookupRequest,
    RegoLookupResponse,
    ShareCreate,
    ShareOut,
    TimelineEventOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Vehicle]:
    return await VehicleService(db).list_for_user(user)


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    payload: VehicleCreate,
    db=Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    svc = VehicleService(db)
    await svc.enforce_limit(user)
    if payload.is_primary:
        await svc.clear_primary(user)
    vehicle = Vehicle(user_id=user.id, **payload.model_dump())
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: str,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> Vehicle:
    vehicle = await VehicleService(db).get_accessible(vehicle_id, user)
    return await VehicleService(db).sync_odometer_from_fuel(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    db=Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    vehicle = await VehicleService(db).get_owned(vehicle_id, user)
    if payload.is_primary:
        await VehicleService(db).clear_primary(user)
    data = payload.model_dump(exclude_unset=True)
    odo_set = data.pop("odometer_km", None)
    for key, value in data.items():
        setattr(vehicle, key, value)
    if odo_set is not None:
        from app.services.odometer import sync_odometer
        await sync_odometer(db, vehicle, odo_set)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=204)
async def delete_vehicle(
    vehicle_id: str,
    db=Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    vehicle = await VehicleService(db).get_owned(vehicle_id, user)
    from app.models.share import VehicleShare
    await db.execute(delete(VehicleShare).where(VehicleShare.vehicle_id == vehicle_id))
    await db.delete(vehicle)
    await db.commit()


@router.post("/rego-lookup", response_model=RegoLookupResponse)
async def rego_lookup(
    payload: RegoLookupRequest,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> RegoLookupResponse:
    """Populate vehicle details from an Australian registration plate + state."""
    from app.services.rate_limit import require_rego_rate_limit
    # Rate-limit check (decorator-style inline to keep the module self-contained)
    await require_rego_rate_limit(user)
    if payload.vehicle_id:
        vehicle = await VehicleService(db).get_accessible(payload.vehicle_id, user)
        owner = await VehicleService(db).get_accessible(payload.vehicle_id, user)
        from app.services.ownership import effective_feature_owner
        owner = await effective_feature_owner(db, vehicle, user)
        if user.role == "demo" or owner.free_account:
            raise HTTPException(
                status_code=403,
                detail="Rego lookup is disabled on the free plan. Upgrade to enable it.",
            )
    elif user.role == "demo" or user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Rego lookup is disabled on the free plan. Upgrade to enable it.",
        )
    result = await VehicleService(db).lookup_rego(
        vehicle if payload.vehicle_id else None,
        owner if payload.vehicle_id else None,
        user,
        payload.rego,
        payload.jurisdiction,
        payload.state,
        payload.vehicle_type,
    )
    if not result:
        raise HTTPException(status_code=404, detail="No registration data found for this plate")
    return RegoLookupResponse(**result)


@router.get("/{vehicle_id}/timeline", response_model=list[TimelineEventOut])
async def get_timeline(
    vehicle_id: str,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    await VehicleService(db).get_accessible(vehicle_id, user)
    return await VehicleService(db).get_timeline(vehicle_id)


@router.post("/{vehicle_id}/shares", response_model=ShareOut, status_code=201)
async def create_share(
    vehicle_id: str,
    payload: ShareCreate,
    db=Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """Share a vehicle with another AutoBrain account by email."""
    await VehicleService(db).get_owned(vehicle_id, user)
    return await VehicleService(db).invite_share(vehicle_id, user, payload.email)


@router.get("/{vehicle_id}/shares", response_model=list[ShareOut])
async def list_shares(
    vehicle_id: str,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await VehicleService(db).get_owned(vehicle_id, user)
    return await VehicleService(db).list_shares(vehicle_id)
