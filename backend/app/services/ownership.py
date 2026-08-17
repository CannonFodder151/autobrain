"""Shared vehicle ownership logic for api/v1 routes.

Extracted from vehicles.py so every vehicle-scoped router enforces the same
ownership, sharing and entitlement rules without duplicating them.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelLog
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle


async def get_owned_vehicle(db: AsyncSession, vehicle_id: str, user: User) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.user_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


async def get_accessible_vehicle(db: AsyncSession, vehicle_id: str, user: User) -> Vehicle:
    """Return a vehicle the user owns or has an accepted share on."""
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if vehicle.user_id == user.id:
        return vehicle
    share = await db.scalar(
        select(VehicleShare).where(
            VehicleShare.vehicle_id == vehicle_id,
            VehicleShare.invitee_user_id == user.id,
            VehicleShare.status == "accepted",
        )
    )
    if share is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


async def effective_feature_owner(db: AsyncSession, vehicle: Vehicle, user: User) -> User:
    """The account whose plan gates a vehicle's features (the owner for shared cars)."""
    if vehicle.user_id == user.id:
        return user
    owner = await db.get(User, vehicle.user_id)
    return owner or user


async def require_ai_vehicle(
    db: AsyncSession, vehicle: Vehicle, user: User
) -> None:
    """AI entitlement for a vehicle-scoped call follows the owner's plan."""
    if user.role == "demo":
        raise HTTPException(
            status_code=403,
            detail="AI features are disabled on the demo account.",
        )
    owner = await effective_feature_owner(db, vehicle, user)
    if owner.free_account:
        raise HTTPException(
            status_code=403,
            detail="AI features are disabled on the free plan. Upgrade to enable them.",
        )


async def require_logbook_enabled(vehicle: Vehicle) -> None:
    """Digital logbook is disabled on club-reg vehicles (product rule [PR-1]):
    Victoria requires the physical VicRoads club log book, so no trip rows may
    be written for club-reg cars — from any source (app or dongle)."""
    if vehicle.club_reg:
        raise HTTPException(
            status_code=403,
            detail=(
                "This vehicle is club-registered — the digital logbook is "
                "disabled (Victoria requires the physical VicRoads club log book)."
            ),
        )


async def clear_primary(db: AsyncSession, user: User) -> None:
    await db.execute(
        Vehicle.__table__.update()
        .where(Vehicle.user_id == user.id)
        .values(is_primary=False)
    )


async def sync_odometer_from_fuel(db: AsyncSession, vehicle: Vehicle) -> Vehicle:
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
