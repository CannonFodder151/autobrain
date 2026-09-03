"""Fuel business logic: efficiency chaining, stats aggregation, receipt intake.

Extracted from api/v1/fuel.py so the router stays thin and the rules are
unit-testable (AUT-126 #12).
"""

import base64
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.storage import detect_mime, ensure_bucket, get_object, upload_object
from app.models.fuel import FuelLog
from app.models.receipt import Receipt
from app.schemas.fuel import FuelLogOut, FuelStats
from app.services.ai_client import extract_fuel_receipt
from app.workers.tasks import queue_embedding

logger = get_logger(__name__)

ALLOWED_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff", "application/pdf"}
MAX_BYTES = 15 * 1024 * 1024


def current_fy(today: date | None = None) -> int:
    """Australian financial year for a date (or now): July-June window."""
    t = today or datetime.now(timezone.utc).date()
    return t.year + (1 if t.month >= 7 else 0)


def ref_time(log: FuelLog) -> datetime:
    return datetime.combine(log.fill_date, datetime.min.time())


async def recompute_efficiency(db: AsyncSession, vehicle_id: str) -> None:
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


async def link_receipt(db: AsyncSession, vehicle_id: str, receipt_id: str | None) -> str | None:
    """Validate a receipt belongs to this vehicle and return its id (or None)."""
    if not receipt_id:
        return None
    r = await db.get(Receipt, receipt_id)
    if not r or r.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Receipt not found for this vehicle")
    return receipt_id


async def compute_fuel_stats(db: AsyncSession, vehicle_id: str) -> FuelStats:
    """Aggregate fuel totals / averages and the ordered series for a vehicle."""
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
    avg_litres = round(sum(r.litres for r in rows) / len(rows), 2) if rows else None
    return FuelStats(
        total_litres=round(total_litres, 2),
        total_cost=round(total_cost, 2),
        avg_l_per_100km=round(sum(x.l_per_100km for x in eff) / len(eff), 2) if eff else None,
        avg_cost_per_km=round(sum(x.cost_per_km for x in costk) / len(costk), 4) if costk else None,
        avg_litres_per_fill=avg_litres,
        last_log=FuelLogOut.model_validate(last) if last else None,
        series=series,
    )


async def upload_fuel_receipt(
    db: AsyncSession,
    vehicle_id: str,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    ai: bool = True,
) -> tuple[Receipt, str, dict]:
    """Store a receipt (with optional OCR) and return (receipt, file_url, parsed).

    Raises HTTPException for size/type violations; the OCR failure path falls
    back to a stored-but-unparsed receipt (AI is best-effort, never blocking).
    """
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    ext = (filename or "receipt").rsplit(".", 1)[-1].lower()
    resolved_type = detect_mime(filename, content_type, data)
    if resolved_type not in ALLOWED_RECEIPT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported receipt file type")
    await ensure_bucket()
    key = f"fuel-receipts/{vehicle_id}/receipt_{uuid.uuid4().hex[:8]}.{ext}"
    url = await upload_object(key, data, resolved_type)
    receipt = Receipt(
        vehicle_id=vehicle_id,
        file_key=key,
        original_name=filename,
        content_type=resolved_type,
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
                "content_base64": base64.b64encode(data).decode() if resolved_type != "application/pdf" else "",
                "content_type": resolved_type,
                "filename": filename,
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
    queue_embedding("receipt", str(receipt.id))
    return receipt, url, parsed


async def receipt_images(logs: list[FuelLog]) -> dict[str, bytes]:
    """Fetch receipt blobs for a set of fuel logs (missing/errored skipped)."""
    images: dict[str, bytes] = {}
    for log in logs:
        if log.receipt and log.receipt.file_key:
            try:
                images[log.receipt.file_key.rsplit("/", 1)[-1]] = await get_object(log.receipt.file_key)
            except Exception:
                continue
    return images
