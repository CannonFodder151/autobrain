"""Celery tasks: async OCR processing, valuation refresh, event fan-out."""

import asyncio
import base64
import io
import json
import logging

from celery import shared_task
from pypdf import PdfReader

from app.core.storage import get_object
from app.db.session import SessionLocal
from app.models.part import Part
from app.models.receipt import ExtractedItem, Receipt
from app.models.service import ServiceRecord
from app.models.valuation import ValuationSnapshot
from app.models.vehicle import Vehicle
from app.services.ai_client import extract_receipt, estimate_value
from app.ws.manager import manager

logger = logging.getLogger("autobrain.workers")

_loop = None


def _run(coro):
    """Run a coroutine on a single persistent loop per worker process.

    The async engine pool binds connections to one loop; using a fresh loop
    per task causes "attached to a different loop" errors.
    """
    global _loop
    try:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
        return _loop.run_until_complete(coro)
    except Exception:
        logger.exception("async_task_failed")
        raise


@shared_task
def process_receipt(receipt_id: str) -> None:
    async def _process():
        async with SessionLocal() as db:
            receipt = await db.get(Receipt, receipt_id)
            if not receipt:
                logger.warning("receipt_not_found", receipt_id=receipt_id)
                return
            receipt.ocr_status = "processing"
            await db.commit()

            file_bytes = await get_object(receipt.file_key)
            content_type = receipt.content_type or ""
            payload: dict = {
                "content": _pdf_text(file_bytes) if content_type == "application/pdf" else "",
                "content_base64": base64.b64encode(file_bytes).decode() if content_type != "application/pdf" else "",
                "content_type": content_type,
                "filename": receipt.original_name,
                "vehicle_id": receipt.vehicle_id,
            }
            result = await extract_receipt(payload)

            if not result:
                receipt.ocr_status = "failed"
                await db.commit()
                return

            receipt.ocr_status = "done"
            receipt.vendor = result.get("vendor")
            receipt.total = result.get("total")
            receipt.tax = result.get("tax")
            receipt.currency = result.get("currency", "AUD")
            receipt.invoice_date = result.get("invoice_date")
            receipt.extracted = json.dumps(result)
            await db.flush()

            for item in result.get("items", []):
                db.add(
                    ExtractedItem(
                        receipt_id=receipt.id,
                        kind=item.get("kind", "part"),
                        name=item.get("name", "Item"),
                        quantity=int(item.get("quantity", 1)),
                        unit_cost=float(item.get("unit_cost", 0.0)),
                        warranty_months=item.get("warranty_months"),
                    )
                )
            await db.commit()
            await manager.send_to_user(
                receipt.vehicle_id,
                "receipt.processed",
                {"receipt_id": receipt.id, "status": "done", "total": receipt.total},
            )

    _run(_process())


@shared_task
def refresh_valuations() -> None:
    async def _refresh():
        async with SessionLocal() as db:
            from sqlalchemy import select

            vehicles = list((await db.scalars(select(Vehicle))).all())
            for vehicle in vehicles:
                services = list((await db.scalars(
                    select(ServiceRecord).where(ServiceRecord.vehicle_id == vehicle.id)
                )).all())
                result = await estimate_value({
                    "vehicle": {
                        "make": vehicle.make, "model": vehicle.model, "year": vehicle.year,
                        "odometer_km": vehicle.odometer_km, "condition": vehicle.condition,
                    },
                    "service_count": len(services),
                })
                if result:
                    db.add(
                        ValuationSnapshot(
                            vehicle_id=vehicle.id,
                            estimated_value=result["estimated_value"],
                            low=result["low"], high=result["high"],
                            currency=result.get("currency", "AUD"),
                            factors=json.dumps(result.get("factors", {})),
                            recommendations=json.dumps(result.get("recommendations", [])),
                        )
                    )
            await db.commit()

    _run(_refresh())


@shared_task
def suggest_reorders() -> None:
    async def _suggest():
        async with SessionLocal() as db:
            from sqlalchemy import select

            parts = list((await db.scalars(select(Part).where(Part.quantity <= Part.min_quantity))).all())
            for part in parts:
                part.ai_reorder_suggestion = (
                    f"Reorder {max(part.min_quantity * 2 - part.quantity, 1)} units "
                    f"({part.quantity} in stock, min {part.min_quantity})."
                )
            await db.commit()

    _run(_suggest())


def _pdf_text(data: bytes) -> str:
    """Extract text from a PDF for downstream OCR/AI extraction."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.exception("pdf_text_extraction_failed")
        return ""
