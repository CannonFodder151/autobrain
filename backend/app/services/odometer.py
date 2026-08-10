"""Shared odometer-sync logic.

Rule (per product): any logged reading bumps the vehicle odometer — fuel
always updates it — unless a *newer* logbook trip exists, in which case the
trip's end reading governs.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
