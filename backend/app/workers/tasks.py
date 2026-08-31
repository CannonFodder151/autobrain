"""Celery tasks: async OCR processing, valuation refresh, event fan-out."""

import asyncio
import base64
import io
import json
from celery import shared_task

from app.core.logging import get_logger
from pypdf import PdfReader

from app.core.storage import get_object
from app.db.session import SessionLocal
from app.models.part import Part
from app.models.receipt import ExtractedItem, Receipt
from app.models.service import ServiceRecord
from app.models.valuation import ValuationSnapshot
from app.models.vehicle import Vehicle
from app.services.ai_client import extract_receipt, estimate_value
from app.services.search import backfill_entity_embedding
from app.ws.manager import manager

logger = get_logger("autobrain.workers")

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
            vehicle = await db.get(Vehicle, receipt.vehicle_id)
            if vehicle:
                await manager.send_to_user(
                    vehicle.user_id,
                    "receipt.processed",
                    {"receipt_id": receipt.id, "status": "done", "total": receipt.total},
                )
            try:
                await backfill_entity_embedding(db, "receipt", receipt.id)
            except Exception:
                logger.exception("receipt_embed_failed")

    _run(_process())


@shared_task
def refresh_valuations() -> None:
    async def _refresh():
        async with SessionLocal() as db:
            from sqlalchemy import func, select

            rows = list((await db.execute(
                select(
                    Vehicle.id, Vehicle.make, Vehicle.model, Vehicle.year,
                    Vehicle.odometer_km, Vehicle.condition,
                    func.count(ServiceRecord.id).label("service_count"),
                )
                .outerjoin(ServiceRecord, ServiceRecord.vehicle_id == Vehicle.id)
                .group_by(Vehicle.id)
            )).all())
            # Fleet can be hundreds of vehicles; the AI gateway times out at
            # 120s, so a serial loop would never finish. Cap concurrency at 4
            # (the DB session is only touched sequentially above and below).
            sem = asyncio.Semaphore(4)

            async def _estimate(row):
                payload = {
                    "vehicle": {
                        "make": row.make, "model": row.model, "year": row.year,
                        "odometer_km": row.odometer_km, "condition": row.condition,
                    },
                    "service_count": row.service_count,
                }
                async with sem:
                    return await estimate_value(payload)

            results = await asyncio.gather(*(_estimate(row) for row in rows))
            for row, result in zip(rows, results):
                if not result:
                    continue
                db.add(
                    ValuationSnapshot(
                        vehicle_id=row.id,
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


@shared_task
def check_due_notifications(vehicle_id: str) -> None:
    """Re-evaluate service-due / fuel-gap notifications for a vehicle."""
    async def _check():
        from app.services.notify import check_vehicle_notifications
        from sqlalchemy import select as sa_select

        async with SessionLocal() as db:
            await check_vehicle_notifications(db, vehicle_id)

    _run(_check())


@shared_task
def run_daily_notification_checks() -> None:
    """Daily sweep: evaluate due notifications across all vehicles."""
    from app.services.notify import run_due_checks

    run_due_checks()


@shared_task
def purge_stale_pending_accounts() -> None:
    """Delete invited/self-signed-up accounts that never completed registration."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.core.config import settings
    from app.models.user import User
    from app.services.backup import delete_user_complete

    async def _purge():
        async with SessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=settings.PENDING_ACCOUNT_RETENTION_DAYS)
            stale = list((await db.scalars(
                select(User).where(User.pending.is_(True), User.created_at < cutoff)
            )).all())
            for user in stale:
                await delete_user_complete(db, user.id)
                logger.info("purged_stale_pending_account", email=user.email, created_at=user.created_at)
            if stale:
                logger.info("purge_stale_pending_done", count=len(stale))

    _run(_purge())


@shared_task
def scheduled_backup() -> None:
    """Daily full-DB snapshot stored to MinIO. Admin backup safety-net."""
    from app.core.config import settings

    if not settings.BACKUP_ENABLED:
        logger.info("scheduled_backup_skipped", reason="BACKUP_ENABLED is False")
        return

    import io as _io
    from datetime import datetime, timezone

    from app.core.storage import get_minio
    from app.services.backup import dump_backup, serialize_all

    async def _do():
        async with SessionLocal() as db:
            data = await serialize_all(db)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            key = f"backups/autobrain-backup-{stamp}.json"
            payload = dump_backup(data)
            get_minio().put_object(
                settings.MINIO_BUCKET, key, _io.BytesIO(payload),
                length=len(payload), content_type="application/json",
            )
            await _prune_backups()
            logger.info("scheduled_backup_done", key=key)

    async def _prune_backups():
        from datetime import timedelta

        from app.core.config import settings
        from app.core.storage import get_minio

        client = get_minio()
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BACKUP_RETENTION_DAYS)
        try:
            for obj in client.list_objects(settings.MINIO_BUCKET, prefix="backups/"):
                if obj.last_modified and obj.last_modified.replace(tzinfo=timezone.utc) < cutoff:
                    client.remove_object(settings.MINIO_BUCKET, obj.object_name)
        except Exception:
            logger.exception("backup_prune_failed")

    _run(_do())


@shared_task
def embed_entity(entity_type: str, entity_id: str) -> bool:
    """Generate and store the embedding for one searchable entity."""
    async def _embed():
        from app.services.search import backfill_entity_embedding

        async with SessionLocal() as db:
            return await backfill_entity_embedding(db, entity_type, entity_id)

    return _run(_embed())

@shared_task
def backfill_entity_embeddings() -> None:
    """Sweep: embed every row missing a vector across all entity types."""
    async def _backfill():
        from sqlalchemy import text

        from app.services.search import _ENTITY_MAP, backfill_entity_embedding

        async with SessionLocal() as db:
            for etype, cfg in _ENTITY_MAP.items():
                table = cfg["model"].__tablename__  # model constant, never user input
                rows = (await db.execute(
                    text(f"SELECT id FROM {table} WHERE {cfg['vector_col']} IS NULL")
                )).all()
                for (entity_id,) in rows:
                    await backfill_entity_embedding(db, etype, entity_id)

    _run(_backfill())


@shared_task
def poll_nsw_fuel_prices() -> None:
    """Daily NSW Fuel API poll (AUT-1813).

    Honours Nathan's constraint: poll once per day per instance (enforced via
    the per-instance poll-state row), never the API quota (2500/month → ~81/day
    headroom at one/day/instance). Falls back silently to the existing cache
    on any transport/HTTP error — the map keeps serving cached prices.
    """
    from datetime import datetime, timezone

    from app.core.config import settings
    from app.services import fuel_prices as fuel_svc

    async def _poll():
        if not fuel_svc.enabled():
            logger.info("nsw_fuel_poll_skipped", reason="disabled_or_unconfigured")
            return
        instance_id = settings.INSTANCE_ID or _hostname()
        async with SessionLocal() as db:
            if not await fuel_svc.should_poll(db, instance_id, "NSW"):
                logger.info("nsw_fuel_poll_skipped", reason="already_polled_today", instance_id=instance_id)
                return
            try:
                records = await fuel_svc.fetch_nsw_prices()
            except Exception:
                logger.exception("nsw_fuel_poll_failed", instance_id=instance_id)
                return
            count = await fuel_svc.store_nsw_prices(db, records)
            await fuel_svc.mark_polled(db, instance_id, "NSW")
            logger.info("nsw_fuel_poll_done", count=count, instance_id=instance_id)

    _run(_poll())


def _hostname() -> str:
    import socket

    return socket.gethostname()


def queue_embedding(entity_type: str, entity_id: str) -> None:
    """Best-effort async embed trigger; a broker hiccup never breaks write paths."""
    try:
        embed_entity.delay(entity_type, entity_id)
    except Exception:
        logger.exception("embed_queue_failed")


def fire_and_forget(task, *args, **kwargs) -> None:
    """Dispatch a Celery task without ever letting a broker failure (e.g. Redis
    down during a worker/restart) break or 500 the caller.

    Several write paths commit their work first and then fan out a best-effort
    background task (due-notifications, async receipt OCR). A broker blip there
    must not turn a successful write into a 500 that the client reads as a
    failed save (AUT-1884). The committed row is the source of truth.
    """
    try:
        task.delay(*args, **kwargs)
    except Exception:
        logger.exception("celery_dispatch_failed", task=getattr(task, "name", repr(task)))


@shared_task
def ingest_fuel_prices() -> None:
    """Scheduled fuel-price pipeline (Servo Spy, AUT-1817).

    Pulls WA FuelWatch, NSW FuelCheck and QLD Fuel Prices into Postgres. Each
    feed is independent — a single feed's failure is logged and does not abort
    the others (see ``app.services.fuel_feeds.ingest_all_fuel``). Deterministic,
    no AI, no spend.
    """
    from app.services.fuel_feeds import ingest_all_fuel

    async def _ingest():
        async with SessionLocal() as db:
            summary = await ingest_all_fuel(db)
            for source, res in summary.items():
                logger.info("fuel_ingest_summary", source=source, **res)
            await db.commit()

    _run(_ingest())


def _pdf_text(data: bytes) -> str:
    """Extract text from a PDF for downstream OCR/AI extraction."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.exception("pdf_text_extraction_failed")
        return ""
