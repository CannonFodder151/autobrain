"""Shared odometer-sync logic.

Source priority (product decision, AUT-1275):
1. Dongle — highest. A dongle trip's end reading is physical truth.
2. Logbook — next. A completed trip's end reading is authoritative.
3. Fuel — least. A fuel receipt reading is a guess taken at fill time.

Hard rule: the odometer only ever moves FORWARD. Any source may advance
it, but no source may roll it back below an existing higher reading — that is
what happens when a user back-fills a past fuel receipt or past logbook trip.
PATCH /vehicles/{id} also routes through this module (AUT-1275 QA fix).
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logbook import LogEntry
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle

_VALID_SERVICE_TYPES = frozenset({
    "scheduled", "tyre_rotation", "air_filter", "brake_fluid", "coolant",
    "transmission", "spark_plugs", "timing_belt", "brake_pads", "battery",
})

# Deterministic manufacturer interval for a scheduled service — mirrors the
# ai/ service-prediction fallback (20,000 km / 12 months) so the suggestion is
# the same whether or not the AI gateway answered (AUT-5318).
_DEFAULT_INTERVAL_KM = 20_000
_DEFAULT_INTERVAL_DAYS = 365
_MIN_MEANINGFUL_GAP_KM = 5_000


def deterministic_next_due(history: list[ServiceRecord], odo: int) -> tuple[int, date]:
    """Next-due km + date from past services alone — no AI, no gateway.

    AUT-5318: the auto-suggest used to bail out entirely when the AI gateway was
    unreachable, so a fuel or logbook write silently created no service item.
    Deterministic-first: the interval comes from the measured gap between
    services, else the manufacturer default.
    """
    points = sorted({s.odometer_km for s in history if s.odometer_km})
    interval_km = _DEFAULT_INTERVAL_KM
    if len(points) >= 2:
        gaps = [b - a for a, b in zip(points, points[1:]) if b - a >= _MIN_MEANINGFUL_GAP_KM]
        if gaps:
            interval_km = round(sum(gaps) / len(gaps))
    next_km = points[-1] + interval_km if points else ((odo // interval_km) + 1) * interval_km

    due_in_days = _DEFAULT_INTERVAL_DAYS
    last_date = max((s.service_date for s in history if s.service_date), default=None)
    if last_date is not None:
        due_in_days = max(_DEFAULT_INTERVAL_DAYS - (date.today() - last_date).days, 0)
    return next_km, date.today() + timedelta(days=due_in_days)


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


async def _ensure_next_service(db: AsyncSession, vehicle: Vehicle) -> None:
    """Board follow-up (AUT-1275): when the odo moves and no scheduled service
    has been set yet, derive the next one from the vehicle's past services via
    the deterministic-first prediction module — AI first, deterministic interval
    when the gateway is down (AUT-5318). Creates regardless of history; the
    due-check then fires when that prediction's threshold is reached.

    Concurrency (QA fix): a Postgres advisory lock serialises the
    check-then-insert so two simultaneous odo writes cannot both create a
    suggestion. On non-Postgres dev fallbacks the lock call is skipped.
    """
    scheduled = await db.scalar(
        select(func.count())
        .select_from(ServiceRecord)
        .where(ServiceRecord.vehicle_id == vehicle.id, ServiceRecord.status == "scheduled")
    )
    if scheduled:
        return

    # ponytail: advisory lock is Postgres-only; sqlite dev fallback skips it —
    # upgrade path is a partial unique index when we drop sqlite.
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"svc-suggest:{vehicle.id}"}
        )
    except Exception:
        pass
    scheduled = await db.scalar(
        select(func.count())
        .select_from(ServiceRecord)
        .where(ServiceRecord.vehicle_id == vehicle.id, ServiceRecord.status == "scheduled")
    )
    if scheduled:
        return

    # AUT-5318: every completed service is usable history. The old
    # filter kept only canonical types, so a vehicle whose records are
    # "repair"/"tyres"/"custom" (or that has none at all) produced an
    # empty history and no service item was ever created.
    from app.services.service_records import list_completed_services

    history = await list_completed_services(db, vehicle.id)

    from app.services.ai_client import predict_service

    last = history[-1] if history else None
    payload = {
        "service_type": "scheduled",
        "odometer_km": vehicle.odometer_km or 0,
        "last_service_km": last.odometer_km if last else None,
        "make": vehicle.make or "",
        "model": vehicle.model or "",
        "year": vehicle.year or date.today().year,
        "vehicle_type": vehicle.vehicle_type or "car",
        "service_history": [
            {
                "service_date": s.service_date.isoformat(),
                "odometer_km": s.odometer_km,
                "service_type": s.service_type,
                "description": s.description,
            }
            for s in history
        ],
    }
    result = await predict_service(payload)
    if not result:
        # AUT-5318: gateway unreachable — fall back to the deterministic
        # interval instead of silently creating nothing.
        next_km, next_due = deterministic_next_due(history, vehicle.odometer_km or 0)
        result = {
            "service_type": "scheduled",
            "next_due_km": next_km,
            "next_due_date": next_due.isoformat(),
            "reason": (
                "Auto-suggested from past service records "
                "(deterministic interval — AI gateway unavailable)"
            ),
        }
    svc_type = str(result.get("service_type") or "scheduled")
    if svc_type not in _VALID_SERVICE_TYPES:
        svc_type = "scheduled"
    due_km = None
    due_date = None
    try:
        raw_km = result.get("next_due_km")
        due_km = int(raw_km) if raw_km else None
    except (TypeError, ValueError):
        pass
    try:
        raw_date = result.get("next_due_date")
        due_date = date.fromisoformat(raw_date) if raw_date else None
    except (TypeError, ValueError):
        pass
    db.add(
        ServiceRecord(
            vehicle_id=vehicle.id,
            service_date=date.today(),
            odometer_km=vehicle.odometer_km or 0,
            service_type=svc_type,
            description=(
                f"Next {svc_type.replace('_', ' ')} "
                "auto-suggested from past service records"
            ),
            status="scheduled",
            ai_prediction=result.get("reason"),
            next_due_km=due_km,
            next_due_date=due_date,
        )
    )


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

    await _ensure_next_service(db, vehicle)

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
        from app.workers.tasks import fire_and_forget, check_due_notifications

        fire_and_forget(check_due_notifications, vehicle.id)