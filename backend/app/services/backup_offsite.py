"""Off-site backup push.

Replaces the standalone backup-agent container (AUT-3827).
Pushes full-DB snapshots to autobrain-backup /ingest endpoint hourly.

Retention is NOT applied here. autobrain-backup owns per-tier retention
(`retention.hourly` / `retention.daily` / `retention.weekly`, engine.py::_prune)
against the same store, pruning by count per tier directory. AUT-5136: the
backend previously ran a second, age-derived retention engine over the same
listing, which collapsed in-policy snapshots (e.g. one per ISO week) and
invented a `monthly` tier the service does not have — 29 of 66 in-policy
snapshots deleted on the first full day of hourly pushes. One owner, one
policy.
"""

import time
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.backup import dump_backup, serialize_all

logger = get_logger("autobrain.backup_offsite")


async def _push_offsite(payload: bytes, filename: str) -> bool:
    """POST backup to the autobrain-backup ingest endpoint.

    AUT-5092: the GUI serves `POST /ingest?instance=<id>` (autobrain-backup
    server.py); the old `/api/backup/ingest` path 404s, so every push failed.
    """
    url = settings.BACKUP_OFFSITE_URL.rstrip("/") + "/ingest"
    params = {"instance": settings.BACKUP_OFFSITE_INSTANCE} if settings.BACKUP_OFFSITE_INSTANCE else {}
    headers = {"Content-Type": "application/json"}
    if settings.BACKUP_OFFSITE_INGEST_KEY:
        headers["X-Ingest-Key"] = settings.BACKUP_OFFSITE_INGEST_KEY
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.post(url, params=params, headers=headers, content=payload)
            r.raise_for_status()
            logger.info("offsite_push_ok", filename=filename, status=r.status_code)
            return True
        except Exception as e:
            logger.error("offsite_push_failed", filename=filename, error=str(e))
            return False


async def run_backup_offsite() -> None:
    """Hourly task: serialize DB and push the snapshot to autobrain-backup.

    Retention is left to the autobrain-backup instance; see module docstring.
    """
    if not settings.BACKUP_OFFSITE_ENABLED:
        logger.info("offsite_backup_skipped", reason="BACKUP_OFFSITE_ENABLED is False")
        return
    if not settings.BACKUP_OFFSITE_URL:
        logger.error("offsite_backup_skipped", reason="BACKUP_OFFSITE_URL not configured")
        return

    started = time.monotonic()
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        data = await serialize_all(db)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"autobrain-backup-{stamp}.json"
        payload = dump_backup(data)

    ok = await _push_offsite(payload, filename)

    logger.info(
        "offsite_backup_done",
        filename=filename,
        size=len(payload),
        tables=len(data.get("data") or {}),
        pushed=ok,
        duration_seconds=round(time.monotonic() - started, 3),
    )