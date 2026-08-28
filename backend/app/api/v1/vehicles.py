"""Vehicle routes: CRUD, rego lookup, timeline."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.rate_limit import require_rego_rate_limit
from app.services.ownership import (
    clear_primary,
    effective_feature_owner,
    get_accessible_vehicle,
    get_owned_vehicle,
    sync_odometer_from_fuel,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import (
    RegoLookupRequest,
    RegoLookupResponse,
    ShareCreate,
    ShareOut,
    TimelineEventOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
)
from app.services.rego import lookup_rego
from app.services.vehicle import (
    enforce_vehicle_limit,
    get_vehicle_timeline,
    invite_share,
    list_user_vehicles,
    list_vehicle_shares,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Vehicle]:
    return await list_user_vehicles(db, user)


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    await enforce_vehicle_limit(db, user)
    if payload.is_primary:
        await clear_primary(db, user)
    vehicle = Vehicle(user_id=user.id, **payload.model_dump())
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Vehicle:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    return await sync_odometer_from_fuel(db, vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    vehicle = await get_owned_vehicle(db, vehicle_id, user)
    if payload.is_primary:
        await clear_primary(db, user)
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    vehicle = await get_owned_vehicle(db, vehicle_id, user)
    await db.execute(
        delete(VehicleShare).where(VehicleShare.vehicle_id == vehicle_id)
    )
    await db.delete(vehicle)
    await db.commit()


@router.post("/rego-lookup", response_model=RegoLookupResponse)
async def rego_lookup(
    payload: RegoLookupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_rego_rate_limit),
) -> RegoLookupResponse:
    """Populate vehicle details from an Australian registration plate + state.

    Free plans can't use rego lookup, except on a vehicle shared with them
    where the owner's plan applies.
    """
    if payload.vehicle_id:
        vehicle = await get_accessible_vehicle(db, payload.vehicle_id, user)
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
    result = await lookup_rego(payload.rego, payload.jurisdiction, payload.state, payload.vehicle_type)
    if not result:
        raise HTTPException(status_code=404, detail="No registration data found for this plate")
    return RegoLookupResponse(**result)


@router.get("/{vehicle_id}/timeline", response_model=list[TimelineEventOut])
async def get_timeline(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    await get_accessible_vehicle(db, vehicle_id, user)
    return await get_vehicle_timeline(db, vehicle_id)


@router.post("/{vehicle_id}/shares", response_model=ShareOut, status_code=201)
async def create_share(
    vehicle_id: str,
    payload: ShareCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """Share a vehicle with another AutoBrain account by email."""
    await get_owned_vehicle(db, vehicle_id, user)
    return await invite_share(db, vehicle_id, user, payload.email)


@router.get("/{vehicle_id}/shares", response_model=list[ShareOut])
async def list_shares(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await get_owned_vehicle(db, vehicle_id, user)
    return await list_vehicle_shares(db, vehicle_id)
