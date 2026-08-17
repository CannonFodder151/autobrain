"""Dongle (trip logger) routes — device keys + unattended trip upload (AUT-918).

Design (decided in AUT-918): the dongle uploads COMPLETE trips via a single
device-scoped batch endpoint instead of reusing the two-phase logbook surface
(POST start + PATCH complete). Reasons:

- The board deep-sleeps between drives and uploads async (often days later), so
  a start/complete pair split across uploads would leave orphan `in_progress`
  rows if the second call ever failed.
- Each uploaded trip carries a stable `device_trip_id` (dongle RTC start time);
  the server keys (device_id, device_trip_id) so WiFi retries are idempotent.
- Device auth (X-Device-API-Key) resolves user + vehicle server-side from the
  binding, so the dongle never carries a short-lived user JWT.

The BLE live-logging path is unchanged; this surface is additive.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_device_from_key, require_write
from app.db.session import get_db
from app.models.device import Device
from app.models.logbook import LogEntry
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.device import (
    DeviceCreate,
    DeviceCreated,
    DeviceOut,
    DeviceTripsIn,
    DeviceTripsResult,
)
from app.services.device_keys import generate_key, hash_key, key_prefix
from app.services.odometer import sync_odometer
from app.services.ownership import get_owned_vehicle, require_logbook_enabled

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Device]:
    stmt = select(Device).where(Device.user_id == user.id).order_by(Device.created_at.desc())
    return list((await db.scalars(stmt)).all())


@router.post("", response_model=DeviceCreated, status_code=201)
async def create_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> DeviceCreated:
    """Create a dongle device and return its one-time API key.

    The plaintext key is only returned here; it is stored hashed. The user
    (or the app, later) must provision it into the dongle via BLE.
    """
    if payload.vehicle_id:
        await get_owned_vehicle(db, payload.vehicle_id, user)
    key = generate_key()
    device = Device(
        user_id=user.id,
        name=(payload.name or "AutoBrain dongle").strip()[:80],
        vehicle_id=payload.vehicle_id,
        api_key_prefix=key_prefix(key),
        api_key_hash=hash_key(key),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceCreated.model_validate(device.__dict__ | {"api_key": key})


@router.post("/{device_id}/trips", response_model=DeviceTripsResult)
async def upload_trips(
    device_id: str,
    payload: DeviceTripsIn,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_key),
) -> DeviceTripsResult:
    """Idempotent batch upload of completed trips from one dongle.

    The dongle authenticated via X-Device-API-Key; the URL path device id must
    match that key's device (the key is the identity — the path just guards
    against a mis-programmed remote URL).
    """
    if device.id != device_id:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.vehicle_id:
        raise HTTPException(
            status_code=409,
            detail="No vehicle bound to this device. Open the app, pair the "
            "dongle, and pick a vehicle first.",
        )
    vehicle = await db.get(Vehicle, device.vehicle_id)
    if vehicle is None or vehicle.user_id != device.user_id:
        raise HTTPException(status_code=409, detail="Bound vehicle is unavailable")
    await require_logbook_enabled(vehicle)

    device.last_seen_at = datetime.now(timezone.utc)
    accepted = 0
    duplicates = 0
    for trip in payload.trips:
        existing = await db.scalar(
            select(LogEntry).where(
                LogEntry.device_id == device.id,
                LogEntry.device_trip_id == trip.device_trip_id,
            )
        )
        if existing:
            duplicates += 1
            continue
        entry = LogEntry(
            vehicle_id=vehicle.id,
            device_id=device.id,
            device_trip_id=trip.device_trip_id,
            source="diy_dongle",
            status="completed",
            purpose=trip.purpose,
            started_at=trip.started_at,
            ended_at=trip.ended_at,
            start_odometer_km=trip.start_odometer_km,
            end_odometer_km=trip.end_odometer_km,
            distance_km=trip.distance_km,
            gps_samples=(
                [s.model_dump() for s in trip.gps_samples]
                if trip.gps_samples is not None
                else None
            ),
        )
        db.add(entry)
        accepted += 1
    await db.flush()
    for trip in payload.trips:
        if trip.end_odometer_km is not None:
            await sync_odometer(db, vehicle, trip.end_odometer_km, trip.ended_at)
    await db.commit()
    return DeviceTripsResult(accepted=accepted, duplicates=duplicates, vehicle_id=vehicle.id)