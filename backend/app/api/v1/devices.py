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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_device_from_key, require_write, verify_dongle_server
from app.db.session import get_db
from app.models.device import Device
from app.models.dongle_firmware import DongleInstalledFirmware
from app.models.logbook import LogEntry
from app.models.obd import ObdCode
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.device import (
    DeviceCodesIn,
    DeviceCreate,
    DeviceCreated,
    DeviceOut,
    DeviceTripsIn,
    DeviceTripsResult,
    DeviceVerifyIn,
    DeviceVerifyOut,
)
from app.services.device_keys import generate_key, hash_key, key_prefix, verify_key
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


@router.post("/verify", dependencies=[Depends(verify_dongle_server)])
async def verify_device(
    payload: DeviceVerifyIn,
    db: AsyncSession = Depends(get_db),
) -> DeviceVerifyOut:
    """Dongle-server backchannel: verify a device's key + serial + paid status
    (AUT-1673).

    The dongle-server (which already checked its local serial whitelist) POSTs
    the hardware serial it read over BLE and the device API key it provisioned.
    We resolve the device from the key hash, compare the stored serial (from the
    device's last firmware report), and check the owning account's paid status.

    Any failure returns serial_matched=False / paid=False — the dongle-server
    interprets that as a 403 and keeps the firmware locked. We never leak
    which check failed to an unauthenticated caller.
    """
    candidates = list(
        (
            await db.scalars(
                select(Device).where(Device.api_key_prefix == key_prefix(payload.api_key))
            )
        ).all()
    )
    device = next(
        (d for d in candidates if verify_key(payload.api_key, d.api_key_hash)), None
    )
    if device is None:
        return DeviceVerifyOut(serial_matched=False, paid=False)
    installed = await db.get(DongleInstalledFirmware, device.id)
    serial_matched = (
        installed is not None
        and installed.serial_number == payload.serial
    )
    user = await db.get(User, device.user_id)
    paid = bool(user and not user.free_account)
    model = installed.model if installed else None
    return DeviceVerifyOut(
        serial_matched=serial_matched,
        paid=paid,
        model=model,
        device_id=device.id,
        user_id=device.user_id,
    )


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

@router.post("/{device_id}/codes", status_code=200)
async def push_codes(
    device_id: str,
    payload: DeviceCodesIn,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_key),
) -> dict:
    """Snapshot of the dongle's current DTC list (AUT-1573).

    The dongle reads stored codes (mode 03) during a trip and pushes the whole
    list here over WiFi; over BLE the app relays the same snapshot. The
    snapshot replaces previous `source=obd` rows on the bound vehicle — manual
    entries are never touched, so retries are idempotent.
    """
    if device.id != device_id:
        raise HTTPException(status_code=404, detail="Device not found")
    owner = await db.get(User, device.user_id)
    if not device.vehicle_id or owner is None:
        raise HTTPException(status_code=409, detail="No vehicle bound to this device")
    vehicle = await db.get(Vehicle, device.vehicle_id)
    if vehicle is None or vehicle.user_id != device.user_id:
        raise HTTPException(status_code=409, detail="Bound vehicle is unavailable")
    if not owner.obd_enabled:
        raise HTTPException(
            status_code=403,
            detail="OBD access is not enabled for this account. Contact your administrator.",
        )
    device.last_seen_at = datetime.now(timezone.utc)

    seen: set[str] = set()
    codes: list = []
    for c in payload.codes:
        if c.code.upper() not in seen:
            seen.add(c.code.upper())
            codes.append(c)
    await db.execute(
        delete(ObdCode).where(ObdCode.vehicle_id == vehicle.id, ObdCode.source == "obd")
    )
    for c in codes:
        db.add(
            ObdCode(
                vehicle_id=vehicle.id,
                code=c.code.upper(),
                description=c.description,
                source="obd",
            )
        )
    await db.commit()
    return {"accepted": len(codes), "vehicle_id": vehicle.id}
