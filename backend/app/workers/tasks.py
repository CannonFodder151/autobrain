"""Celery tasks: async OCR processing, valuation refresh, event fan-out."""

import asyncio
import base64
import io
import json
import time
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
    except RuntimeError as exc:
        # "Event loop is closed" / "Future attached to a different loop" — the
        # persistent loop is wedged (e.g. one task killed the loop). Recreate
        # it on the next call so a single bad task does not poison the rest
        # of the worker (AUT-2256: hosted scheduled_backup failure class).
        if "closed" in str(exc).lower() or "different loop" in str(exc).lower():
            logger.warning("async_task_loop_recreate", error=str(exc))
            try:
                _loop.close()
            except Exception:
                pass
            _loop = None
        logger.exception("async_task_failed")
        raise
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
def check_fuel_price_alerts() -> None:
    """AUT-1859: evaluate servo-spy watch lists against the latest prices.

    Deterministic-first: a pure price-change comparison (no AI) decides whether
    each watched station/fuel-type crossed the user's % threshold since the
    previous day. Alerts reuse the user's existing notification channels.

    Runs after the daily NSW poll so it evaluates fresh data; it also runs
    standalone (beat) so cached-snapshot-only instances still alert.
    """
    from datetime import date

    from sqlalchemy import select

    from app.models.fuel_price import FuelPriceSnapshot, FuelPriceWatchlist
    from app.services.fuel_prices import compute_price_change
    from app.services.notify import deliver_fuel_price_alert

    async def _run():
        async with SessionLocal() as db:
            watch_ids = list((await db.scalars(select(FuelPriceWatchlist.id))).all())
            for wid in watch_ids:
                w = await db.get(FuelPriceWatchlist, wid)
                if not w:
                    continue
                fp = await db.scalar(
                    select(FuelPriceSnapshot).where(
                        FuelPriceSnapshot.state == w.state,
                        FuelPriceSnapshot.station_code == w.station_code,
                        FuelPriceSnapshot.fuel_type == w.fuel_type,
                    )
                )
                if not fp:
                    logger.info("fuel_alert_no_price", watch_id=wid, station=w.station_code)
                    continue
                pct, direction = compute_price_change(fp.price, fp.previous_price)
                if direction is None:
                    continue  # not enough history yet (first poll) — no alert
                if w.direction not in ("both", direction):
                    continue
                if abs(pct) < w.threshold_pct:
                    continue
                # One alert per (user, station, fuel, direction, day).
                day = date.today().isoformat()
                kind = f"fuel_price:{direction}:{w.station_code}:{w.fuel_type}:{day}"
                label = (fp.brand or fp.station_name or "Station")
                title = f"{label} {fp.fuel_type} price {direction} {abs(pct):.1f}%"
                description = (
                    f"{fp.station_name or w.station_code} {fp.fuel_type}: "
                    f"{fp.previous_price} → {fp.price} c/L "
                    f"({'%.1f' % pct}% vs yesterday)"
                )
                await deliver_fuel_price_alert(db, w.user_id, kind, title, description)
                logger.info("fuel_alert_evaluated", watch_id=wid, direction=direction, pct=pct)

    _run(_run())


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


_MINIO_PUT_ATTEMPTS = 3
_MINIO_PUT_BACKOFF = 0.5


def _minio_put_with_retry(client, bucket: str, key: str, data: bytes, content_type: str) -> None:
    """Upload to MinIO with retries on transient failures."""
    import io as _io

    for attempt in range(_MINIO_PUT_ATTEMPTS):
        try:
            client.put_object(
                bucket, key, _io.BytesIO(data), length=len(data), content_type=content_type
            )
            return
        except Exception as exc:
            if attempt == _MINIO_PUT_ATTEMPTS - 1:
                raise
            logger.warning("minio_put_retry", attempt=attempt + 1, key=key, error=str(exc))
            time.sleep(_MINIO_PUT_BACKOFF * (attempt + 1))


@shared_task
def scheduled_backup() -> None:
    """Daily full-DB snapshot stored to MinIO. Admin backup safety-net.

    AUT-2256: hosted backups were silently failing because (a) minio secrets
    missing on the worker → empty creds raise on every put, (b) one bad task
    poisoned the persistent event loop so subsequent tasks ran on a wedged
    loop, (c) the prune path raised on transient errors and turned the whole
    job into a Celery FAIL with no recoverable signal. Now: skip-with-loud-log
    on missing config (no Celery failure spam), reset a wedged loop, and
    isolate the prune so a prune error never fails the upload.
    """
    from app.core.config import settings

    if not settings.BACKUP_ENABLED:
        logger.info("scheduled_backup_skipped", reason="BACKUP_ENABLED is False")
        return
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        logger.error(
            "scheduled_backup_skipped",
            reason="minio_credentials_missing",
            bucket=settings.MINIO_BUCKET,
            endpoint=settings.MINIO_ENDPOINT,
        )
        return

    import io as _io
    from datetime import datetime, timezone

    from app.core.storage import get_minio
    from app.services.backup import dump_backup, serialize_all

    async def _do():
        started = time.monotonic()
        async with SessionLocal() as db:
            data = await serialize_all(db)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            key = f"backups/autobrain-backup-{stamp}.json"
            payload = dump_backup(data)
            _minio_put_with_retry(get_minio(), settings.MINIO_BUCKET, key, payload, "application/json")
            try:
                await _prune_backups()
            except Exception:
                # Prune is best-effort retention, never let it fail the daily
                # snapshot upload — a successful put with a prune error is
                # better than a Celery FAIL that loses the snapshot.
                logger.exception("backup_prune_top_level_failed")
            logger.info(
                "scheduled_backup_done",
                key=key,
                size=len(payload),
                tables=len(data.get("data") or {}),
                duration_seconds=round(time.monotonic() - started, 3),
            )

    async def _prune_backups():
        from datetime import timedelta

        from app.core.config import settings
        from app.core.storage import get_minio

        client = get_minio()
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BACKUP_RETENTION_DAYS)
        pruned = 0
        try:
            for obj in client.list_objects(settings.MINIO_BUCKET, prefix="backups/"):
                if obj.last_modified and obj.last_modified.replace(tzinfo=timezone.utc) < cutoff:
                    client.remove_object(settings.MINIO_BUCKET, obj.object_name)
                    pruned += 1
        except Exception:
            logger.exception("backup_prune_failed")
        if pruned:
            logger.info("backup_prune_done", count=pruned)

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
            # AUT-1859: re-evaluate servo-spy alerts against the freshly cached prices.
            check_fuel_price_alerts.delay()

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
def ingest_fuel_all() -> None:
    """Scheduled fuel-price pipeline (Servo Spy, AUT-1817 + AUT-2375).

    Runs every enabled feed (WA FuelWatch, NSW FuelCheck, QLD DirectAPI, and
    SA/TAS/NT once AUT-2374 ships them) into Postgres. Each feed is independent
    — a single feed's failure is logged and does not abort the others (see
    ``app.services.fuel_feeds.ingest_all_fuel``). Deterministic, no AI, no spend.

    Beat fires this ONCE per day at 02:00 AEST (off-peak); the /fuel/stations and
    /fuel/stations/{id}/history endpoints only serve cached DB rows so they
    never fan out to upstream APIs on a client request.
    """
    from app.services.fuel_feeds import ingest_all_fuel

    async def _ingest():
        async with SessionLocal() as db:
            summary = await ingest_all_fuel(db)
            for source, res in summary.items():
                logger.info("fuel_ingest_summary", source=source, **res)
            await db.commit()

    _run(_ingest())


# Backwards-compat alias so older dispatch sites / dashboards keep working
# while the beat schedule migrates. Will be removed once no caller is left.
ingest_fuel_prices = ingest_fuel_all


def _run_single_source_ingest(source: str, fn) -> dict:
    """Run a single ``ingest_<source>_*`` ingestor and return its summary."""
    from app.services import fuel_feeds as feeds

    async def _ingest():
        async with SessionLocal() as db:
            res = await fn(db)
            logger.info("fuel_ingest_summary", source=source, **res)
            await db.commit()
            return res

    return _run(_ingest())


@shared_task
def ingest_fuel_wa() -> None:
    """AUT-2375: per-source manual-trigger ingest (WA FuelWatch)."""
    from app.services.fuel_feeds import ingest_wa_fuelwatch

    return _run_single_source_ingest("wa", ingest_wa_fuelwatch)


@shared_task
def ingest_fuel_nsw() -> None:
    """AUT-2375: per-source manual-trigger ingest (NSW FuelCheck)."""
    from app.services.fuel_feeds import ingest_nsw_fuelcheck

    return _run_single_source_ingest("nsw", ingest_nsw_fuelcheck)


@shared_task
def ingest_fuel_qld() -> None:
    """AUT-2375: per-source manual-trigger ingest (QLD Fuel Prices)."""
    from app.services.fuel_feeds import ingest_qld_fuel_prices

    return _run_single_source_ingest("qld", ingest_qld_fuel_prices)


@shared_task
def refresh_sca_parts_cache() -> dict:
    """Nightly SCA parts cache prewarm (AUT-2419).

    Walks every distinct (make, model, year) in the vehicles table and forces
    a fresh SCA lookup so the next user click returns from cache. Failures on
    individual vehicles are logged and skipped — one bad vehicle never aborts
    the rest. The return dict is logged as ``sca_cache_prewarm_done`` so
    ops can graph duration/success over the first few runs.
    """
    from app.services import parts_guide

    async def _prewarm() -> dict:
        async with SessionLocal() as db:
            sigs = await parts_guide.list_vehicle_signatures(db)
        if not sigs:
            logger.info("sca_cache_prewarm_done", vehicles=0, ok=0, failed=0,
                        duration_s=0.0)
            return {"vehicles": 0, "ok": 0, "failed": 0, "duration_s": 0.0}

        sem = asyncio.Semaphore(4)

        async def _one(sig: dict) -> str:
            async with sem:
                try:
                    async with SessionLocal() as db:
                        await parts_guide.lookup_sca_parts(
                            db, make=sig["make"] or "", model=sig["model"] or "",
                            year=sig["year"], refresh=True,
                        )
                    return "ok"
                except Exception:
                    logger.exception("sca_cache_prewarm_vehicle_failed",
                                     make=sig["make"], model=sig["model"],
                                     year=sig["year"])
                    return "failed"

        started = time.monotonic()
        outcomes = await asyncio.gather(*(_one(s) for s in sigs))
        duration = time.monotonic() - started
        ok = sum(1 for o in outcomes if o == "ok")
        failed = len(outcomes) - ok
        summary = {"vehicles": len(sigs), "ok": ok, "failed": failed,
                   "duration_s": round(duration, 2)}
        logger.info("sca_cache_prewarm_done", **summary)
        return summary

    return _run(_prewarm())


def _pdf_text(data: bytes) -> str:
    """Extract text from a PDF for downstream OCR/AI extraction."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.exception("pdf_text_extraction_failed")
        return ""
