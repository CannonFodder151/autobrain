"""Shared odometer-sync logic.

Source priority (product decision, AUT-1275):
1. Dongle — highest. A dongle trip's end reading is physical truth.
2. Logbook — next. A completed trip's end reading is authoritative.
3. Fuel — least. A fuel receipt reading is a guess taken at fill time.

Hard rule: the odometer only ever moves FORWARD. Any source reading advances
it, but no source may roll it back below an existing higher reading — that is
what happens when a user back-fills a past fuel receipt or past logbook trip.

The one surface that can lower the odometer is an explicit owner edit via
PATCH /vehicles/{id} (maintenance correction) — that path writes
vehicle.odometer_km directly and intentionally bypasses this module.
"""

from datetime import date, datetime

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
) -> bool:
    """Apply a logged odometer reading to the vehicle.

    `ref_time` is when the reading was taken (defaults to now). A completed
    trip that ended *after* that moment is treated as physical truth and takes
    precedence over the logged-in reading.

    Returns True when the odometer actually moved, so callers can trigger
    follow-ups (e.g. the auto service suggestion).
    """
    if source_odo is None:
        return False
    prev = vehicle.odometer_km or 0
    candidate = source_odo
    newest = await _newest_logbook_entry(db, vehicle.id)
    if (
        newest
        and newest.end_odometer_km
        and newest.ended_at
        and (ref_time is None or newest.ended_at > ref_time)
    ):
        candidate = max(candidate, newest.end_odometer_km)
    target = max(prev, candidate)
    vehicle.odometer_km = target
    if target > prev and vehicle.auto_suggest_service:
        await suggest_due_service(db, vehicle)
    return target > prev


async def suggest_due_service(db: AsyncSession, vehicle: Vehicle) -> None:
    """AUT-1275: when auto-suggest is on and the odometer has reached an
    upcoming service's due threshold, surface a suggestion.

    Deterministic — a pure odo/due-threshold comparison, no AI call per write.
    The due thresholds themselves come from the deterministic-first service
    prediction module in `ai/`. Each upcoming service is reported once and
    deduplicated via the ``service_due`` timeline event.
    """
    from app.services.events import add_event
    from app.models.service import ServiceRecord
    from app.models.vehicle import VehicleEvent

    odo = vehicle.odometer_km or 0
    today = date.today()
    rows = await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle.id,
            ServiceRecord.status == "scheduled",
        )
    )
    triggered = False
    for svc in rows:
        reached = (
            svc.next_due_km is not None and odo >= svc.next_due_km
        ) or (svc.next_due_date is not None and today >= svc.next_due_date)
        if not reached:
            continue
        existing = await db.scalar(
            select(VehicleEvent.id).where(
                VehicleEvent.source_id == svc.id,
                VehicleEvent.event_type == "service_due",
            )
        )
        if existing:
            continue
        label = svc.service_type.replace("_", " ").title()
        if svc.next_due_km:
            title = f"{label} due — next service suggested at {svc.next_due_km:,} km"
        else:
            title = f"{label} due — next service suggested"
        await add_event(
            db, vehicle.id, "service_due", title, today, odo, None, svc.id
        )
        triggered = True
    if triggered:
        from app.workers.tasks import check_due_notifications

        check_due_notifications.delay(vehicle.id)