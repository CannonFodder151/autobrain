"""Fuel tracker routes."""

import base64
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.api.v1.vehicles import add_event, _get_owned_vehicle
from app.core.logging import get_logger
from app.core.storage import detect_mime, ensure_bucket, get_object, upload_object
from app.db.session import get_db
from app.models.fuel import FuelLog
from app.models.receipt import Receipt
from app.models.user import User
from app.schemas.fuel import (
    FuelLogCreate,
    FuelLogOut,
    FuelLogUpdate,
    FuelStats,
    FuelReceiptResult,
)
from app.services.ai_client import extract_fuel_receipt
from app.services.export import export_fuel_csv, export_zip
from app.services.odometer import sync_odometer

router = APIRouter(prefix="/vehicles/{vehicle_id}/fuel", tags=["fuel"])

logger = get_logger(__name__)

ALLOWED_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff", "application/pdf"}
MAX_BYTES = 15 * 1024 * 1024


def _current_fy() -> int:
    today = datetime.now(timezone.utc)
    return today.year + (1 if today.month >= 7 else 0)


async def _recompute_efficiency(db: AsyncSession, vehicle_id: str) -> None:
    """Recompute L/100km / cost-per-km for every full-tank fill of a vehicle.

    Runs after any add/update/delete so back-filled (older-odometer) entries
    still get an efficiency, and later fills are re-chained correctly. Logs
    with a non-positive distance (duplicate or out-of-order odometer) are
    left without an efficiency rather than given a wrong one.
    """
    rows = await db.scalars(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.odometer_km, FuelLog.fill_date)
    )
    prev: FuelLog | None = None
    for log in rows:
        log.distance_km = None
        log.l_per_100km = None
        log.cost_per_km = None
        if log.is_full_tank and prev and prev.is_full_tank:
            distance = log.odometer_km - prev.odometer_km
            if distance > 0:
                log.distance_km = distance
                log.l_per_100km = round(log.litres / distance * 100, 2)
                log.cost_per_km = round(log.total_cost / distance, 4)
        if log.is_full_tank:
            prev = log


def _ref_time(log: FuelLog) -> datetime:
    return datetime.combine(log.fill_date, datetime.min.time())


@router.get("", response_model=list[FuelLogOut])
async def list_fuel(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FuelLog]:
    """List fuel logs, optionally filtered to an Australian financial year
    (e.g. fy=2026 covers 2025-07-01 .. 2026-06-30)."""
    await _get_owned_vehicle(db, vehicle_id, user)
    q = select(FuelLog).where(FuelLog.vehicle_id == vehicle_id)
    if fy:
        q = q.where(FuelLog.fill_date >= date(fy - 1, 7, 1), FuelLog.fill_date <= date(fy, 6, 30))
    rows = await db.scalars(q.order_by(FuelLog.fill_date.desc()))
    return list(rows)


async def _link_receipt(db: AsyncSession, vehicle_id: str, receipt_id: str | None) -> str | None:
    """Validate a receipt belongs to this vehicle and return its id (or None)."""
    if not receipt_id:
        return None
    r = await db.get(Receipt, receipt_id)
    if not r or r.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Receipt not found for this vehicle")
    return receipt_id


@router.post("", response_model=FuelLogOut, status_code=201)
async def add_fuel(
    vehicle_id: str,
    payload: FuelLogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelLog:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    total = payload.total_cost if payload.total_cost else round(payload.litres * payload.price_per_litre, 2)
    receipt_id = await _link_receipt(db, vehicle_id, payload.receipt_id)
    log = FuelLog(
        vehicle_id=vehicle_id,
        total_cost=total,
        receipt_id=receipt_id,
        **payload.model_dump(exclude={"total_cost", "receipt_id"}),
    )
    db.add(log)
    await db.flush()
    await _recompute_efficiency(db, vehicle_id)
    await sync_odometer(db, vehicle, payload.odometer_km, _ref_time(log))
    await add_event(
        db,
        vehicle_id,
        "fuel",
        f"Fuel {payload.litres:.1f}L @ {payload.odometer_km:,} km",
        payload.fill_date,
        payload.odometer_km,
        total,
        log.id,
    )
    await db.commit()
    await db.refresh(log)
    from app.workers.tasks import check_due_notifications
    check_due_notifications.delay(vehicle_id)
    return log


@router.patch("/{fuel_id}", response_model=FuelLogOut)
async def update_fuel(
    vehicle_id: str,
    fuel_id: str,
    payload: FuelLogUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelLog:
    await _get_owned_vehicle(db, vehicle_id, user)
    log = await db.get(FuelLog, fuel_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Fuel log not found")
    data = payload.model_dump(exclude_unset=True)
    if "receipt_id" in data:
        data["receipt_id"] = await _link_receipt(db, vehicle_id, data["receipt_id"])
    if "total_cost" in data and data["total_cost"] is None:
        data.pop("total_cost")
    if data.get("total_cost") is None:
        data["total_cost"] = round(
            data.get("litres", log.litres) * data.get("price_per_litre", log.price_per_litre), 2
        )
    for key, value in data.items():
        setattr(log, key, value)
    if log.odometer_km <= 0:
        raise HTTPException(status_code=422, detail="odometer_km must be positive")
    await _recompute_efficiency(db, vehicle_id)
    await db.flush()
    await sync_odometer(db, await _get_owned_vehicle(db, vehicle_id, user), log.odometer_km, _ref_time(log))
    await db.commit()
    await db.refresh(log)
    return log


@router.delete("/{fuel_id}", status_code=204)
async def delete_fuel(
    vehicle_id: str,
    fuel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await _get_owned_vehicle(db, vehicle_id, user)
    log = await db.get(FuelLog, fuel_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Fuel log not found")
    await db.delete(log)
    await _recompute_efficiency(db, vehicle_id)
    await db.commit()


@router.get("/stats", response_model=FuelStats)
async def fuel_stats(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FuelStats:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = list(
        (
            await db.scalars(
                select(FuelLog)
                .where(FuelLog.vehicle_id == vehicle_id)
                .order_by(FuelLog.fill_date.asc())
            )
        ).all()
    )
    totals = await db.execute(
        select(
            func.coalesce(func.sum(FuelLog.litres), 0),
            func.coalesce(func.sum(FuelLog.total_cost), 0),
        ).where(FuelLog.vehicle_id == vehicle_id)
    )
    total_litres, total_cost = totals.one()
    eff = [r for r in rows if r.l_per_100km is not None]
    costk = [r for r in rows if r.cost_per_km is not None]
    series = [
        {
            "date": str(r.fill_date),
            "odometer": r.odometer_km,
            "l_per_100km": r.l_per_100km,
            "cost_per_km": r.cost_per_km,
            "price_per_litre": r.price_per_litre,
        }
        for r in rows
    ]
    last = rows[-1] if rows else None
    return FuelStats(
        total_litres=round(total_litres, 2),
        total_cost=round(total_cost, 2),
        avg_l_per_100km=round(sum(x.l_per_100km for x in eff) / len(eff), 2) if eff else None,
        avg_cost_per_km=round(sum(x.cost_per_km for x in costk) / len(costk), 4) if costk else None,
        last_log=FuelLogOut.model_validate(last) if last else None,
        series=series,
    )


@router.get("/export")
async def export_fuel_year(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    fmt: str = Query("csv", pattern="^(csv|zip)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Export fuel records for an Australian financial year (tax purposes).

    fmt=zip bundles the CSV (with an Image column) plus the receipt images.
    """
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    fy = fy or _current_fy()
    start = datetime(fy - 1, 7, 1)
    end = datetime(fy, 6, 30, 23, 59, 59)
    logs = list((await db.scalars(
        select(FuelLog).where(
            FuelLog.vehicle_id == vehicle_id,
            FuelLog.fill_date >= start.date(),
            FuelLog.fill_date <= end.date(),
        ).order_by(FuelLog.fill_date)
    )).all())
    content = export_fuel_csv(logs, fy)
    label = vehicle.nickname.replace(" ", "-")
    if fmt == "csv":
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="fuel-{label}-FY{fy-1}-{str(fy)[2:]}.csv"'},
        )
    images: dict[str, bytes] = {}
    for log in logs:
        if log.receipt and log.receipt.file_key:
            try:
                images[log.receipt.file_key.rsplit("/", 1)[-1]] = await get_object(log.receipt.file_key)
            except Exception:
                continue
    zipped = export_zip(content, images)
    return Response(
        content=zipped,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="fuel-{label}-FY{fy-1}-{str(fy)[2:]}-with-images.zip"'},
    )


@router.post("/receipt", response_model=FuelReceiptResult, status_code=201)
async def upload_fuel_receipt(
    vehicle_id: str,
    file: UploadFile = File(...),
    ai: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelReceiptResult:
    """Upload a fuel receipt photo.

    With ai=true (paid accounts) the receipt is OCR'd to fill litres and
    price-per-litre. ai=false just stores the photo — the user fills the
    values manually.
    """
    await _get_owned_vehicle(db, vehicle_id, user)
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    ext = (file.filename or "receipt").rsplit(".", 1)[-1].lower()
    content_type = detect_mime(file.filename, file.content_type, data)
    if content_type not in ALLOWED_RECEIPT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported receipt file type")
    await ensure_bucket()
    key = f"fuel-receipts/{vehicle_id}/receipt_{uuid.uuid4().hex[:8]}.{ext}"
    url = await upload_object(key, data, content_type)
    receipt = Receipt(
        vehicle_id=vehicle_id,
        file_key=key,
        original_name=file.filename,
        content_type=content_type,
        ocr_status="done" if not ai else "pending",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)

    parsed: dict = {}
    if ai:
        try:
            parsed = await extract_fuel_receipt({
                "content": "",
                "content_base64": base64.b64encode(data).decode() if content_type != "application/pdf" else "",
                "content_type": content_type,
                "filename": file.filename,
                "vehicle_id": vehicle_id,
            }) or {}
        except Exception:
            logger.exception("fuel_receipt_ai_failed")
            parsed = {}
        receipt.ocr_status = "done" if parsed else "failed"
        if parsed:
            receipt.vendor = parsed.get("vendor")
            receipt.total = parsed.get("total_cost")
            receipt.invoice_date = parsed.get("date")
    else:
        receipt.ocr_status = "done"
    await db.commit()
    await db.refresh(receipt)

    return FuelReceiptResult(
        receipt_id=receipt.id,
        file_url=url,
        vendor=parsed.get("vendor"),
        date=parsed.get("date"),
        litres=parsed.get("litres"),
        price_per_litre=parsed.get("price_per_litre"),
        total_cost=parsed.get("total_cost"),
        currency=parsed.get("currency", "AUD"),
        ai_used=bool(ai and parsed),
    )

