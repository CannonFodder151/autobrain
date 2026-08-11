"""Logbook (ATO trip) routes.

Only available on vehicles WITHOUT club reg. Product rule [PR-1] (see
docs/product-rules.md): in Victoria, club-permit vehicles must keep the
physical VicRoads club log book, so the digital logbook is disabled for
club-registered vehicles. Trips can be started with time/date/GPS/odo and
completed later with an end time/date/odo — completing a trip updates the
vehicle odometer (a logbook reading is authoritative over older fuel entries).

DELETE stays available on club-reg vehicles so stale entries can be cleaned up.
"""

import base64
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle, require_ai_vehicle
from app.core.storage import detect_mime, ensure_bucket, upload_object
from app.db.session import get_db
from app.models.logbook import LogEntry
from app.models.user import User
from app.schemas.logbook import (
    LogEntryCreate,
    LogEntryOut,
    LogEntryUpdate,
    LogbookStats,
    OdometerPhotoResult,
)
from app.services.ai_client import read_odometer
from app.services.odometer import sync_odometer

router = APIRouter(prefix="/vehicles/{vehicle_id}/logbook", tags=["logbook"])


def _require_logbook(vehicle) -> None:
    if vehicle.club_reg:
        raise HTTPException(
            status_code=403,
            detail=(
                "This vehicle is club-registered — the digital logbook is "
                "disabled (Victoria requires the physical VicRoads club log book)."
            ),
        )


def _fy_bounds(fy: int) -> tuple[datetime, datetime]:
    """Australian financial year ends 30 June. fy=2026 covers 2025-07-01..2026-06-30."""
    start = datetime(fy - 1, 7, 1, tzinfo=timezone.utc)
    end = datetime(fy, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _current_fy() -> int:
    today = datetime.now(timezone.utc)
    return today.year + (1 if today.month >= 7 else 0)


async def _recompute_distance(entry: LogEntry) -> None:
    if entry.end_odometer_km and entry.start_odometer_km:
        entry.distance_km = max(entry.end_odometer_km - entry.start_odometer_km, 0)


@router.post("", response_model=LogEntryOut, status_code=201)
async def start_trip(
    vehicle_id: str,
    payload: LogEntryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> LogEntry:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    entry = LogEntry(vehicle_id=vehicle_id, status="in_progress", **payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("", response_model=list[LogEntryOut])
async def list_entries(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LogEntry]:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    stmt = select(LogEntry).where(LogEntry.vehicle_id == vehicle_id)
    if fy:
        start, end = _fy_bounds(fy)
        stmt = stmt.where(LogEntry.started_at >= start, LogEntry.started_at <= end)
    stmt = stmt.order_by(LogEntry.started_at.desc())
    return list((await db.scalars(stmt)).all())


@router.get("/stats", response_model=LogbookStats)
async def logbook_stats(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LogbookStats:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    stmt = select(LogEntry).where(LogEntry.vehicle_id == vehicle_id)
    if fy:
        start, end = _fy_bounds(fy)
        stmt = stmt.where(LogEntry.started_at >= start, LogEntry.started_at <= end)
    rows = list((await db.scalars(stmt)).all())
    total_km = sum(r.distance_km or 0 for r in rows)
    work = [r for r in rows if r.purpose == "work"]
    work_km = sum(r.distance_km or 0 for r in work)
    pct = round(work_km / total_km * 100, 2) if total_km else 0.0
    return LogbookStats(
        total_trips=len(rows),
        total_distance_km=round(total_km, 1),
        work_trips=len(work),
        work_distance_km=round(work_km, 1),
        work_percentage=pct,
    )


@router.patch("/{entry_id}", response_model=LogEntryOut)
async def update_entry(
    vehicle_id: str,
    entry_id: str,
    payload: LogEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> LogEntry:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    entry = await db.get(LogEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Log entry not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(entry, key, value)
    if entry.ended_at or entry.status == "completed":
        entry.status = "completed"
        entry.ended_at = entry.ended_at or datetime.now(timezone.utc)
    # A caller-provided distance (e.g. GPS odometer diff from the phone car-kit
    # path, AUT-367) is authoritative; otherwise derive from the odometer diff.
    if "distance_km" not in data:
        await _recompute_distance(entry)
    await db.flush()
    if entry.status == "completed" and entry.end_odometer_km:
        await sync_odometer(db, vehicle, entry.end_odometer_km, entry.ended_at)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    vehicle_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    entry = await db.get(LogEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Log entry not found")
    await db.delete(entry)
    await db.commit()


@router.get("/export")
async def export_logbook(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """CSV export for ATO logbook claims, per Australian financial year."""
    from app.services.export import export_logbook_csv

    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    fy = fy or _current_fy()
    rows = list((await db.scalars(
        select(LogEntry)
        .where(LogEntry.vehicle_id == vehicle_id)
        .order_by(LogEntry.started_at)
    )).all())
    content = export_logbook_csv(rows, fy)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="logbook-{vehicle.nickname.replace(" ", "-")}-FY{fy-1}-{str(fy)[2:]}.csv"'},
    )


@router.post("/odometer-photo", response_model=OdometerPhotoResult)
async def read_odometer_photo(
    vehicle_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OdometerPhotoResult:
    """OCR a dashboard photo to read the odometer (start/end of a trip)."""
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    _require_logbook(vehicle)
    await require_ai_vehicle(db, vehicle, user)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    result = await read_odometer({
        "content": "",
        "content_base64": base64.b64encode(data).decode(),
        "content_type": detect_mime(file.filename, file.content_type, data),
        "filename": file.filename,
    })
    if not result:
        raise HTTPException(status_code=503, detail="Odometer OCR engine unavailable")
    return OdometerPhotoResult(**result)
