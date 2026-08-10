"""Vehicle business logic: listing (owned + shared), timeline, share invites.

Extracted from api/v1/vehicles.py so the router stays thin and the queries
are unit-testable (AUT-126 #12).
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ownership import sync_odometer_from_fuel
from app.models.service import ServiceRecord
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleEvent


async def list_user_vehicles(db: AsyncSession, user: User) -> list[Vehicle]:
    """The user's owned vehicles followed by cars shared with them (accepted)."""
    owned = list((await db.scalars(
        select(Vehicle).where(Vehicle.user_id == user.id).order_by(Vehicle.created_at.desc())
    )).all())
    shared = (await db.execute(
        select(Vehicle, User)
        .join(VehicleShare, VehicleShare.vehicle_id == Vehicle.id)
        .join(User, User.id == Vehicle.user_id)
        .where(
            VehicleShare.invitee_user_id == user.id,
            VehicleShare.status == "accepted",
        )
        .order_by(Vehicle.created_at.desc())
    )).all()
    for v in owned:
        await sync_odometer_from_fuel(db, v)
        v.is_shared = False
        v.shared_by = None
    for v, owner in shared:
        await sync_odometer_from_fuel(db, v)
        v.is_shared = True
        v.shared_by = owner.display_name
    return owned + [v for v, _owner in shared]


async def enforce_vehicle_limit(db: AsyncSession, user: User) -> None:
    """Raise 403 when the user has hit their vehicle-creation limit."""
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


async def get_vehicle_timeline(db: AsyncSession, vehicle_id: str) -> list[VehicleEvent]:
    """Timeline events, dropping service events that are not yet completed."""
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


async def invite_share(db: AsyncSession, vehicle_id: str, owner: User, email: str) -> dict:
    """Share a vehicle with another AutoBrain account by email (validated)."""
    email = email.strip().lower()
    invitee = await db.scalar(select(User).where(User.email == email))
    if not invitee:
        raise HTTPException(status_code=404, detail="No AutoBrain account with that email")
    if invitee.id == owner.id:
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


async def list_vehicle_shares(db: AsyncSession, vehicle_id: str) -> list[dict]:
    """All shares on a vehicle (with invitee details), newest first."""
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
