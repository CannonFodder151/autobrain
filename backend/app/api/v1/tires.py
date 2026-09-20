"""Tire inventory & usage tracking routes.

Deterministic-first: heat cycles counted from session count, tread wear
predicted via compound lookup tables, end-of-life alerts computed from pure
arithmetic — no AI dependency.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.notification import NotificationDelivery, NotificationPreference
from app.models.tire import (
    MIN_TREAD_MM,
    COMPOUND_LIFE_KM,
    COMPOUND_NEW_TREAD_MM,
    TireSet,
    TireSession,
    TireTreadReading,
)
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.tire import (
    TireSessionCreate,
    TireSessionOut,
    TireSessionUpdate,
    TireSetCreate,
    TireSetOut,
    TireSetUpdate,
    TireTreadReadingCreate,
    TireTreadReadingOut,
    TireTreadReadingUpdate,
)

router = APIRouter(prefix="/vehicles/{vehicle_id}/tires", tags=["tires"])


async def _get_vehicle(db: AsyncSession, vehicle_id: str, user: User) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.user_id != user.id:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


# --- Tire Sets ---

@router.get("", response_model=list[TireSetOut])
async def list_tire_sets(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TireSetOut]:
    await _get_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(TireSet).where(TireSet.vehicle_id == vehicle_id).order_by(TireSet.created_at.desc())
    )
    return list(rows)


@router.post("", response_model=TireSetOut, status_code=201)
async def create_tire_set(
    vehicle_id: str,
    payload: TireSetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireSetOut:
    await _get_vehicle(db, vehicle_id, user)
    # Default new_tread_mm from compound if not provided
    if payload.new_tread_mm is None:
        payload.new_tread_mm = COMPOUND_NEW_TREAD_MM.get(payload.compound, 8.0)
    ts = TireSet(vehicle_id=vehicle_id, **payload.model_dump())
    db.add(ts)
    await db.commit()
    await db.refresh(ts)
    return ts


@router.get("/{tire_set_id}", response_model=TireSetOut)
async def get_tire_set(
    vehicle_id: str,
    tire_set_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TireSetOut:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    return ts


@router.patch("/{tire_set_id}", response_model=TireSetOut)
async def update_tire_set(
    vehicle_id: str,
    tire_set_id: str,
    payload: TireSetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireSetOut:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(ts, key, value)
    await db.commit()
    await db.refresh(ts)
    return ts


@router.delete("/{tire_set_id}", status_code=204)
async def delete_tire_set(
    vehicle_id: str,
    tire_set_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    await db.delete(ts)
    await db.commit()


@router.get("/alerts", response_model=list[dict])
async def tire_alerts(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Check all tire sets for end-of-life or approaching end-of-life alerts.

    Deterministic: alerts fire when predicted_remaining_km < 20% of
    effective_life OR tread depth is at/below MIN_TREAD_MM.
    """
    await _get_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(TireSet)
        .where(TireSet.vehicle_id == vehicle_id, TireSet.status == "active")
        .options(
            selectinload(TireSet.sessions),
            selectinload(TireSet.tread_readings),
        )
    )
    alerts = []
    for ts in rows:
        remaining = ts.predicted_remaining_km
        life_pct = ts.end_of_life_pct
        current_tread = ts.remaining_tread_mm
        base_life = COMPOUND_LIFE_KM.get(ts.compound, 25000)
        cycles = ts.heat_cycles
        if cycles:
            cycle_factor = max(0.1, 1.0 - cycles * 0.03)
            effective_life = base_life * cycle_factor
        else:
            effective_life = base_life
        alert = None
        if ts.is_end_of_life:
            alert = {
                "tire_set_id": ts.id,
                "name": ts.name,
                "type": "end_of_life",
                "severity": "critical",
                "message": f"Tires at or below {MIN_TREAD_MM}mm tread depth — replace immediately",
                "current_tread_mm": current_tread,
                "minimum_tread_mm": MIN_TREAD_MM,
            }
        elif remaining is not None and remaining < effective_life * 0.2:
            alert = {
                "tire_set_id": ts.id,
                "name": ts.name,
                "type": "approaching_end_of_life",
                "severity": "warning",
                "message": f"Tires approaching end of life — {round(remaining)} km predicted remaining",
                "predicted_remaining_km": round(remaining),
                "heat_cycles": cycles,
                "life_pct_remaining": round(life_pct, 1) if life_pct else None,
            }
        if alert:
            alerts.append(alert)
    return alerts


# --- Tire Sessions ---

@router.get("/{tire_set_id}/sessions", response_model=list[TireSessionOut])
async def list_sessions(
    vehicle_id: str,
    tire_set_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TireSessionOut]:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    rows = await db.scalars(
        select(TireSession).where(TireSession.tire_set_id == tire_set_id).order_by(TireSession.session_date.desc())
    )
    return list(rows)


@router.post("/{tire_set_id}/sessions", response_model=TireSessionOut, status_code=201)
async def create_session(
    vehicle_id: str,
    tire_set_id: str,
    payload: TireSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireSessionOut:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    session = TireSession(tire_set_id=tire_set_id, **payload.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    # Fire notification check for tire alerts after new session
    await _check_tire_notifications(db, vehicle_id, user.id)
    return session


@router.patch("/{tire_set_id}/sessions/{session_id}", response_model=TireSessionOut)
async def update_session(
    vehicle_id: str,
    tire_set_id: str,
    session_id: str,
    payload: TireSessionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireSessionOut:
    await _get_vehicle(db, vehicle_id, user)
    session = await db.get(TireSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Verify session belongs to this tire set / vehicle
    ts = await db.get(TireSet, session.tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, key, value)
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{tire_set_id}/sessions/{session_id}", status_code=204)
async def delete_session(
    vehicle_id: str,
    tire_set_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_vehicle(db, vehicle_id, user)
    session = await db.get(TireSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ts = await db.get(TireSet, session.tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    await db.delete(session)
    await db.commit()


# --- Tread Readings ---

@router.get("/{tire_set_id}/tread-readings", response_model=list[TireTreadReadingOut])
async def list_tread_readings(
    vehicle_id: str,
    tire_set_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TireTreadReadingOut]:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    rows = await db.scalars(
        select(TireTreadReading)
        .where(TireTreadReading.tire_set_id == tire_set_id)
        .order_by(TireTreadReading.reading_date.desc())
    )
    return list(rows)


@router.post("/{tire_set_id}/tread-readings", response_model=TireTreadReadingOut, status_code=201)
async def create_tread_reading(
    vehicle_id: str,
    tire_set_id: str,
    payload: TireTreadReadingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireTreadReadingOut:
    await _get_vehicle(db, vehicle_id, user)
    ts = await db.get(TireSet, tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    reading = TireTreadReading(tire_set_id=tire_set_id, **payload.model_dump())
    db.add(reading)
    await db.commit()
    await db.refresh(reading)
    # Check if new reading triggers end-of-life notification
    await _check_tire_notifications(db, vehicle_id, user.id)
    return reading


@router.patch("/{tire_set_id}/tread-readings/{reading_id}", response_model=TireTreadReadingOut)
async def update_tread_reading(
    vehicle_id: str,
    tire_set_id: str,
    reading_id: str,
    payload: TireTreadReadingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> TireTreadReadingOut:
    await _get_vehicle(db, vehicle_id, user)
    reading = await db.get(TireTreadReading, reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    ts = await db.get(TireSet, reading.tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(reading, key, value)
    await db.commit()
    await db.refresh(reading)
    return reading


@router.delete("/{tire_set_id}/tread-readings/{reading_id}", status_code=204)
async def delete_tread_reading(
    vehicle_id: str,
    tire_set_id: str,
    reading_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_vehicle(db, vehicle_id, user)
    reading = await db.get(TireTreadReading, reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    ts = await db.get(TireSet, reading.tire_set_id)
    if not ts or ts.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Tire set not found")
    await db.delete(reading)
    await db.commit()


# --- Notifications ---

async def _check_tire_notifications(db: AsyncSession, vehicle_id: str, user_id: str) -> None:
    """Evaluate tire end-of-life alerts and record notification deliveries.

    Uses deterministic thresholds (no AI): fires when a tire set is at end of
    life, or predicted to be within 20% of effective life remaining. Dedupes
    per (vehicle_id, kind) so we don't spam repeated alerts for the same set.
    """
    # Check user's notification preference for this vehicle
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.vehicle_id == vehicle_id,
        )
    )

    # Only alert if user has push notifications enabled or has a global pref
    if not pref or (not pref.push_enabled and not pref.email_enabled):
        return

    tire_sets = await db.scalars(
        select(TireSet)
        .where(TireSet.vehicle_id == vehicle_id, TireSet.status == "active")
        .options(
            selectinload(TireSet.sessions),
            selectinload(TireSet.tread_readings),
        )
    )

    for ts in tire_sets:
        kind = f"tires:{ts.id}"
        existing = await db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.vehicle_id == vehicle_id,
                NotificationDelivery.kind == kind,
            )
        )
        if existing:
            continue  # already alerted for this set

        if ts.is_end_of_life:
            db.add(
                NotificationDelivery(
                    vehicle_id=vehicle_id,
                    user_id=user_id,
                    kind=kind,
                    channels="push,email",
                )
            )
            await db.commit()
            await _send_tire_notification(
                user_id, ts, "end_of_life",
                f"{ts.name} ({ts.brand} {ts.model}) tread at or below {MIN_TREAD_MM}mm — replace now",
            )
        elif ts.end_of_life_pct is not None and ts.end_of_life_pct >= 80:
            db.add(
                NotificationDelivery(
                    vehicle_id=vehicle_id,
                    user_id=user_id,
                    kind=kind,
                    channels="push,email",
                )
            )
            await db.commit()
            await _send_tire_notification(
                user_id, ts, "approaching_end_of_life",
                f"{ts.name} ({ts.brand} {ts.model}) at {round(ts.end_of_life_pct, 1)}% life consumed — {round(ts.predicted_remaining_km or 0)} km remaining",
            )


async def _send_tire_notification(user_id: str, tire_set: TireSet, kind: str, message: str) -> None:
    """Record a tire alert notification. Actual delivery is via push/email services."""
    from app.ws.manager import manager

    await manager.send_to_user(
        user_id,
        "tire.alert",
        {
            "tire_set_id": tire_set.id,
            "name": tire_set.name,
            "type": kind,
            "message": message,
        },
    )
