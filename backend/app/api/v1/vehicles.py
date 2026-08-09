"""Vehicle routes: CRUD, rego lookup, timeline."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_rego, require_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.service import ServiceRecord
from app.models.fuel import FuelLog
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleEvent
from app.models.share import VehicleShare
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

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles", tags=["vehicles"])


async def _get_owned_vehicle(db: AsyncSession, vehicle_id: str, user: User) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.user_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Vehicle]:
    rows = list((await db.scalars(
        select(Vehicle).where(Vehicle.user_id == user.id).order_by(Vehicle.created_at.desc())
    )).all())
    for v in rows:
        await _sync_odometer_from_fuel(db, v)
    return rows


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    count = await db.scalar(
        select(func.count()).select_from(Vehicle).where(Vehicle.user_id == user.id)
    )
    if (count or 0) >= user.max_vehicles:
        remaining = max(user.max_vehicles - (count or 0), 0)
        raise HTTPException(
            status_code=403,
            detail=f"Vehicle limit reached ({user.max_vehicles}). "
            f"You have {remaining} slot(s) left on this account.",
        )
    if payload.is_primary:
        await _clear_primary(db, user)
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
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    return await _sync_odometer_from_fuel(db, vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Vehicle:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    if payload.is_primary:
        await _clear_primary(db, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(vehicle, key, value)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=204)
async def delete_vehicle(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    await db.delete(vehicle)
    await db.commit()


@router.post("/rego-lookup", response_model=RegoLookupResponse)
async def rego_lookup(
    payload: RegoLookupRequest,
    _user: User = Depends(require_rego),
) -> RegoLookupResponse:
    """Populate vehicle details from an Australian registration plate + state."""
    result = await lookup_rego(payload.rego, payload.jurisdiction, payload.state, payload.vehicle_type)
    if not result:
        raise HTTPException(status_code=404, detail="No registration data found for this plate")
    return RegoLookupResponse(**result)


@router.get("/{vehicle_id}/timeline", response_model=list[TimelineEventOut])
async def get_timeline(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VehicleEvent]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(VehicleEvent)
        .outerjoin(ServiceRecord, ServiceRecord.id == VehicleEvent.source_id)
        .where(
            VehicleEvent.vehicle_id == vehicle_id,
            or_(
                VehicleEvent.event_type != "service",
                and_(
                    ServiceRecord.status == "completed",
                    VehicleEvent.occurred_on <= date.today(),
                ),
            ),
        )
        .order_by(VehicleEvent.occurred_on.desc(), VehicleEvent.created_at.desc())
    )
    return list(rows)

@router.post("/{vehicle_id}/shares", response_model=ShareOut, status_code=201)
async def create_share(
    vehicle_id: str,
    payload: ShareCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """Share a vehicle with another AutoBrain account by email."""
    await _get_owned_vehicle(db, vehicle_id, user)
    email = payload.email.strip().lower()
    invitee = await db.scalar(select(User).where(User.email == email))
    if not invitee:
        raise HTTPException(status_code=404, detail="No AutoBrain account with that email")
    if invitee.id == user.id:
        raise HTTPException(status_code=400, detail="You can't share a vehicle with yourself")
    existing = await db.scalar(
        select(VehicleShare).where(
            VehicleShare.vehicle_id == vehicle_id,
            VehicleShare.invitee_user_id == invitee.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Vehicle already shared with this account")
    share = VehicleShare(vehicle_id=vehicle_id, invitee_user_id=invitee.id)
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return {
        "id": share.id,
        "vehicle_id": share.vehicle_id,
        "invitee_user_id": invitee.id,
        "invitee_email": invitee.email,
        "invitee_display_name": invitee.display_name,
        "status": share.status,
        "created_at": share.created_at,
    }

@router.get("/{vehicle_id}/shares", response_model=list[ShareOut])
async def list_shares(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = (await db.execute(
        select(VehicleShare, User)
        .join(User, VehicleShare.invitee_user_id == User.id)
        .where(VehicleShare.vehicle_id == vehicle_id)
        .order_by(VehicleShare.created_at.desc())
    )).all()
    return [
        {
            "id": s.id,
            "vehicle_id": s.vehicle_id,
            "invitee_user_id": u.id,
            "invitee_email": u.email,
            "invitee_display_name": u.display_name,
            "status": s.status,
            "created_at": s.created_at,
        }
        for s, u in rows
    ]


async def _clear_primary(db: AsyncSession, user: User) -> None:
    await db.execute(
        Vehicle.__table__.update()
        .where(Vehicle.user_id == user.id)
        .values(is_primary=False)
    )


async def _sync_odometer_from_fuel(db: AsyncSession, vehicle: Vehicle) -> Vehicle:
    """Backfill odometer from fuel logs only when the vehicle has none set.

    Manual edits to `odometer_km` are authoritative and are never overridden by
    fuel data (a user may correct the clock after a gap in logging).
    """
    if vehicle.odometer_km:
        return vehicle
    latest = await db.scalar(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle.id)
        .order_by(FuelLog.odometer_km.desc())
    )
    if latest and latest.odometer_km > 0:
        vehicle.odometer_km = latest.odometer_km
    return vehicle


# --- event materialisation (called by other routers after writes) ---
async def add_event(
    db: AsyncSession,
    vehicle_id: str,
    event_type: str,
    title: str,
    occurred_on,
    odometer_km: int | None,
    amount: float | None,
    source_id: str,
) -> None:
    db.add(
        VehicleEvent(
            vehicle_id=vehicle_id,
            event_type=event_type,
            title=title,
            occurred_on=occurred_on,
            odometer_km=odometer_km,
            amount=amount,
            source_id=source_id,
        )
    )
