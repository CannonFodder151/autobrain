"""Shared odometer-sync logic.

Rule (per product): any logged reading bumps the vehicle odometer — fuel
always updates it — unless a *newer* logbook trip exists, in which case the
trip's end reading governs.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelLog
from app.models.logbook import LogEntry
from app.models.vehicle import Vehicle


async def _newest_logbook_entry(db: AsyncSession, vehicle_id: str) -> LogEntry | None:
    return await db.scalar(
        select(LogEntry)
        .where(LogEntry.vehicle_id == vehicle_id, LogEntry.ended_at.isnot(None))
        .order_by(LogEntry.ended_at.desc())
    )


async def sync_odometer(
    db: AsyncSession, vehicle: Vehicle, source_odo: int | None, ref_time: datetime | None = None
) -> None:
    """Apply a logged odometer reading to the vehicle, deferring to any newer
    logbook trip. `ref_time` is when the reading was taken (defaults to now)."""
    if source_odo is None:
        return
    newest = await _newest_logbook_entry(db, vehicle.id)
    if newest and newest.end_odometer_km and ref_time and newest.ended_at and newest.ended_at > ref_time:
        vehicle.odometer_km = max(vehicle.odometer_km or 0, newest.end_odometer_km)
        return
    vehicle.odometer_km = source_odo


async def sync_odometer_from_fuel(
    db: AsyncSession, vehicles: list[Vehicle]
) -> list[Vehicle]:
    """Backfill `odometer_km` for vehicles that have none set, from logged
    readings. Batched: one MAX(odometer_km) query per fuel source + one query
    for newest completed logbook trips, so list endpoints don't run a query per
    vehicle. A completed logbook trip governs over fuel (single product rule,
    matching `sync_odometer`).
    """
    pending = [v for v in vehicles if not v.odometer_km]
    if not pending:
        return vehicles
    ids = [v.id for v in pending]

    fuel_rows = (await db.execute(
        select(FuelLog.vehicle_id, func.max(FuelLog.odometer_km))
        .where(FuelLog.vehicle_id.in_(ids), FuelLog.odometer_km > 0)
        .group_by(FuelLog.vehicle_id)
    )).all()
    max_fuel = {vehicle_id: odo for vehicle_id, odo in fuel_rows}

    trip_rows = (await db.execute(
        select(LogEntry.vehicle_id, LogEntry.end_odometer_km)
        .where(
            LogEntry.vehicle_id.in_(ids),
            LogEntry.ended_at.isnot(None),
            LogEntry.end_odometer_km.isnot(None),
        )
        .order_by(LogEntry.ended_at.desc())
    )).all()
    newest_trip: dict[str, int] = {}
    for vehicle_id, odo in trip_rows:
        newest_trip.setdefault(vehicle_id, odo)

    for v in pending:
        if v.id in newest_trip:
            v.odometer_km = newest_trip[v.id]
        elif v.id in max_fuel:
            v.odometer_km = max_fuel[v.id]
    return vehicles
