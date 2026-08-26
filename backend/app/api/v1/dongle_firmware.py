"""Dongle firmware OTA manifest + installed-firmware telemetry (AUT-1673).

Surface:

- ``GET /dongle/firmware/latest?model=…`` — returns the newest manifest for
  that model (user-authenticated; the app uses it to decide whether an update
  is available).
- ``POST /dongle/firmware/report`` — the dongle POSTs its current model,
  firmware version and serial number over the device-authenticated channel
  (X-Device-API-Key). The row in ``dongle_installed_firmware`` lets the app
  render "Update available" without a fresh BLE read.
- ``GET /dongle/firmware/installed`` — the app reads its own installed
  firmware for the linked device.
- ``POST /dongle/firmware`` — admin-only; publishes a new manifest (the blob
  itself is uploaded to MinIO by ops, then the row is created here).

The OTA payload itself is chunked over BLE (characteristic
``6E400005-…DCCA9E``); the API is intentionally just the manifest + telemetry.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_device_from_key,
    require_admin,
)
from app.core.storage import presigned_url
from app.db.session import get_db
from app.models.device import Device
from app.models.dongle_firmware import (
    DongleFirmware,
    DongleInstalledFirmware,
)
from app.models.user import User
from app.schemas.dongle_firmware import (
    DongleFirmwareCreate,
    DongleFirmwareOut,
    DongleInstalledFirmwareOut,
    DongleInstalledFirmwareReport,
)

router = APIRouter(prefix="/dongle", tags=["dongle"])


def _to_manifest(row: DongleFirmware, signed: str) -> DongleFirmwareOut:
    return DongleFirmwareOut(
        model=row.model,
        version=row.version,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        release_notes=row.release_notes,
        created_at=row.created_at,
        blob_url=signed,
    )


@router.get("/firmware/latest", response_model=DongleFirmwareOut | None)
async def latest_firmware(
    model: str = Query(min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DongleFirmwareOut | None:
    """Newest firmware manifest for [model]. Returns null (200 OK) when no
    release has been published yet — consistent with [installed_firmware],
    which also returns null rather than 404 so the app can treat "never
    reported" and "no release published" with the same null check.
    """
    row = await db.scalar(
        select(DongleFirmware)
        .where(DongleFirmware.model == model)
        .order_by(DongleFirmware.created_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    signed = await presigned_url(row.blob_key)
    return _to_manifest(row, signed)


@router.get("/firmware/installed", response_model=DongleInstalledFirmwareOut | None)
async def installed_firmware(
    device_id: str = Query(min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DongleInstalledFirmwareOut | None:
    """Installed firmware row for one of THIS user's devices. Null = never reported.

    [device_id] is the ``Device.id`` primary key (a UUID string), the same value
    the app receives from ``GET /devices`` and stores as ``DongleDevice.id`` —
    NOT the hardware serial (which is read over BLE and only used on the
    unauthenticated /report write). The ``db.get`` calls below are primary-key
    lookups on that UUID, so the app↔server identifier mapping is exact; a
    mismatched UUID yields 404, never a silent null.
    """
    device = await db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status_code=404, detail="Device not found")
    row = await db.get(DongleInstalledFirmware, device_id)
    if row is None:
        return None
    return DongleInstalledFirmwareOut.model_validate(row.__dict__)


@router.post(
    "/firmware/report",
    response_model=DongleInstalledFirmwareOut,
    status_code=status.HTTP_200_OK,
)
async def report_installed_firmware(
    payload: DongleInstalledFirmwareReport,
    db: AsyncSession = Depends(get_db),
    device: Device = Depends(get_device_from_key),
) -> DongleInstalledFirmwareOut:
    """Dongle reports its current model / firmware / serial. Device-authenticated.

    idempotent: an existing row for this device is updated in place; the first
    report creates it. This is the write that lets the app render
    "firmware v1.4.2 on OBD Logging Device V1" and "Update available".

    Retention / growth: ``dongle_installed_firmware.device_id`` is the primary
    key and a FK on ``devices.id ON DELETE CASCADE`` — one row per active
    device, removed automatically when the device is deleted, so the table is
    bounded by the fleet size, not by report frequency. No background vacuuming
    is required.
    """
    row = await db.get(DongleInstalledFirmware, device.id)
    if row is None:
        row = DongleInstalledFirmware(
            device_id=device.id,
            model=payload.model,
            firmware_version=payload.firmware_version,
            serial_number=payload.serial_number,
            last_reported_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.model = payload.model
        row.firmware_version = payload.firmware_version
        row.serial_number = payload.serial_number
        row.last_reported_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return DongleInstalledFirmwareOut.model_validate(row.__dict__)


@router.post(
    "/firmware",
    response_model=DongleFirmwareOut,
    status_code=status.HTTP_201_CREATED,
)
async def publish_firmware(
    payload: DongleFirmwareCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DongleFirmwareOut:
    """Admin-only: register a new firmware manifest.

    The blob itself is uploaded to MinIO by ops (so this API never has to
    carry multi-MB firmware payloads over the LB); this call records only the
    manifest. Re-publishing the same (model, version) is rejected — use a new
    version string.
    """
    del admin  # authorization is the side effect
    existing = await db.scalar(
        select(DongleFirmware).where(
            DongleFirmware.model == payload.model,
            DongleFirmware.version == payload.version,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Firmware {payload.version} for {payload.model} already exists",
        )
    row = DongleFirmware(
        model=payload.model,
        version=payload.version,
        sha256=payload.sha256,
        size_bytes=payload.size_bytes,
        blob_key=payload.blob_key,
        release_notes=payload.release_notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    signed = await presigned_url(row.blob_key)
    return _to_manifest(row, signed)
