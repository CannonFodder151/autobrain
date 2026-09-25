"""Vehicle domain service layer.

All vehicle CRUD, timeline, sharing, and rego-lookup persistence lives here.
The FastAPI router in ``api.py`` delegates to these functions so business
logic stays unit-testable without an HTTP server.
"""

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ownership import (
    clear_primary,
    effective_feature_owner,
    get_accessible_vehicle,
    get_owned_vehicle,
    sync_odometer_from_fuel,
)
from app.services.rego import lookup_rego
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle


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
    from sqlalchemy import func
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


async def get_vehicle_timeline(db: AsyncSession, vehicle_id: str) -> list:
    """Timeline events, dropping service events that are not yet completed."""
    from app.models.service import ServiceRecord
    from app.models.vehicle import VehicleEvent
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


async def persist_rego_on_vehicle(db: AsyncSession, vehicle: Vehicle, result: dict) -> None:
    """Cache rego status + expiry on the vehicle after a successful lookup."""
    vehicle.rego_status = result.get("status") or "registered"
    expiry_raw = result.get("expiry_date")
    if expiry_raw:
        try:
            vehicle.rego_expiry_date = date.fromisoformat(expiry_raw)
        except (ValueError, TypeError):
            vehicle.rego_expiry_date = None
    else:
        vehicle.rego_expiry_date = None
    vehicle.rego_checked_at = datetime.now(timezone.utc)
    await db.commit()


async def lookup_rego_for_vehicle(
    db: AsyncSession,
    vehicle: Vehicle,
    owner: User,
    caller: User,
    rego: str,
    jurisdiction: str,
    state: str,
    vehicle_type: str,
) -> dict:
    """Run a rego lookup and persist the result on the vehicle."""
    if caller.role == "demo" or owner.free_account:
        raise HTTPException(
            status_code=403,
            detail="Rego lookup is disabled on the free plan. Upgrade to enable it.",
        )
    result = await lookup_rego(rego, jurisdiction, state, vehicle_type)
    if not result:
        raise HTTPException(status_code=404, detail="No registration data found for this plate")
    await persist_rego_on_vehicle(db, vehicle, result)
    return result


class VehicleService:
    """High-level facade over vehicle domain operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, user: User) -> list[Vehicle]:
        return await list_user_vehicles(self.db, user)

    async def enforce_limit(self, user: User) -> None:
        await enforce_vehicle_limit(self.db, user)

    async def clear_primary(self, user: User) -> None:
        await clear_primary(self.db, user)

    async def get_accessible(self, vehicle_id: str, user: User) -> Vehicle:
        return await get_accessible_vehicle(self.db, vehicle_id, user)

    async def get_owned(self, vehicle_id: str, user: User) -> Vehicle:
        return await get_owned_vehicle(self.db, vehicle_id, user)

    async def sync_odometer_from_fuel(self, vehicle: Vehicle) -> Vehicle:
        return await sync_odometer_from_fuel(self.db, vehicle)

    async def get_timeline(self, vehicle_id: str) -> list:
        return await get_vehicle_timeline(self.db, vehicle_id)

    async def invite_share(self, vehicle_id: str, owner: User, email: str) -> dict:
        return await invite_share(self.db, vehicle_id, owner, email)

    async def list_shares(self, vehicle_id: str) -> list[dict]:
        return await list_vehicle_shares(self.db, vehicle_id)

    async def lookup_rego(
        self,
        vehicle: Vehicle,
        owner: User,
        caller: User,
        rego: str,
        jurisdiction: str,
        state: str,
        vehicle_type: str,
    ) -> dict:
        return await lookup_rego_for_vehicle(
            self.db, vehicle, owner, caller, rego, jurisdiction, state, vehicle_type
        )

__all__ = [
    "VehicleService",
    "list_user_vehicles",
    "enforce_vehicle_limit",
    "get_vehicle_timeline",
    "invite_share",
    "list_vehicle_shares",
    "persist_rego_on_vehicle",
    "lookup_rego_for_vehicle",
]
