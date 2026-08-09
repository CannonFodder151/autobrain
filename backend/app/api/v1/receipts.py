"""Receipt & parts scanner routes (OCR + AI extraction)."""

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.api.v1.vehicles import _get_accessible_vehicle
from app.core.logging import get_logger
from app.core.storage import delete_object, detect_mime, ensure_bucket, upload_object
from app.db.session import get_db
from app.models.part import Part, PartMovement
from app.models.receipt import ExtractedItem, Receipt
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.schemas.receipt import ApplyToServiceRequest, ReceiptOut
from app.workers.tasks import process_receipt

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles/{vehicle_id}/receipts", tags=["receipts"])

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}
ALLOWED_EXTS = {"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif", "tiff", "tif"}
MAX_BYTES = 15 * 1024 * 1024


def _ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return "bin"
    return filename.rsplit(".", 1)[-1].lower()


@router.post("", response_model=ReceiptOut, status_code=201)
async def upload_receipt(
    vehicle_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Receipt:
    await _get_accessible_vehicle(db, vehicle_id, user)
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")
    content_type = detect_mime(file.filename, file.content_type, data)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.filename or file.content_type}. "
            "Supported: PDF, JPG, PNG, WEBP, HEIC.",
        )
    await ensure_bucket()
    key = f"receipts/{vehicle_id}/{Receipt.__tablename__}_upload_{_rand()}.{_ext(file.filename)}"
    url = await upload_object(key, data, content_type)
    receipt = Receipt(
        vehicle_id=vehicle_id,
        file_key=key,
        original_name=file.filename,
        content_type=content_type,
        ocr_status="pending",
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    process_receipt.delay(receipt.id)
    return receipt


@router.get("", response_model=list[ReceiptOut])
async def list_receipts(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Receipt]:
    await _get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Receipt).where(Receipt.vehicle_id == vehicle_id).order_by(Receipt.created_at.desc())
    )
    return list(rows)


@router.delete("/{receipt_id}", status_code=204)
async def delete_receipt(
    vehicle_id: str,
    receipt_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    """Delete a scanned receipt (e.g. one stuck on 'pending' after OCR failed)."""
    await _get_accessible_vehicle(db, vehicle_id, user)
    receipt = await db.get(Receipt, receipt_id)
    if not receipt or receipt.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    from app.models.fuel import FuelLog

    linked = await db.scalar(select(FuelLog).where(FuelLog.receipt_id == receipt_id))
    if linked:
        raise HTTPException(
            status_code=409,
            detail="Receipt is attached to a fuel record — remove it from the fuel log first",
        )
    await db.execute(delete(ExtractedItem).where(ExtractedItem.receipt_id == receipt_id))
    file_key = receipt.file_key
    await db.delete(receipt)
    await db.commit()
    try:
        await delete_object(file_key)
    except Exception:
        pass


@router.post("/{receipt_id}/apply-to-service", response_model=ReceiptOut)
async def apply_receipt_to_service(
    vehicle_id: str,
    receipt_id: str,
    payload: ApplyToServiceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Receipt:
    await _get_accessible_vehicle(db, vehicle_id, user)
    receipt = await db.get(Receipt, receipt_id)
    if not receipt or receipt.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.ocr_status != "done":
        raise HTTPException(status_code=409, detail="Receipt not extracted yet")

    service = ServiceRecord(
        vehicle_id=vehicle_id,
        service_date=_today(),
        odometer_km=0,
        service_type=payload.service_type,
        workshop=payload.workshop or receipt.vendor,
        cost=receipt.total or 0.0,
        currency=receipt.currency,
        notes=payload.notes or f"From scanned receipt {receipt.original_name or receipt_id}",
        photo_keys=[receipt.file_key],
    )
    db.add(service)
    await db.flush()

    items = await db.scalars(select(ExtractedItem).where(ExtractedItem.receipt_id == receipt_id))
    for item in items:
        db.add(
            ServiceItem(
                service_id=service.id,
                name=item.name,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
            )
        )
        if item.kind == "part" and payload.add_parts_to_inventory:
            part = await db.scalar(
                select(Part).where(
                    Part.vehicle_id == vehicle_id,
                    Part.sku == item.name.lower().replace(" ", "-"),
                )
            )
            if part:
                part.quantity += item.quantity
            else:
                part = Part(
                    vehicle_id=vehicle_id,
                    name=item.name,
                    sku=item.name.lower().replace(" ", "-"),
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    warranty_months=item.warranty_months,
                )
                db.add(part)
                await db.flush()
            db.add(PartMovement(part_id=part.id, delta=item.quantity, reason="scan", service_id=service.id))
        item.applied_to_service = True
    await db.commit()
    await db.refresh(receipt)
    return receipt


def _rand() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _today():
    from datetime import date
    return date.today()

