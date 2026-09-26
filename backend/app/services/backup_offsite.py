"""Off-site backup push with tiered retention.

Replaces the standalone backup-agent container (AUT-3827).
Pushes full-DB snapshots to autobrain-backup /ingest endpoint hourly.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.storage import get_minio
from app.services.backup import dump_backup, serialize_all

logger = logging.getLogger("autobrain.backup_offsite")


def _tier_for_age(hours_old: int) -> str | None:
    """Return tier name if the snapshot should be kept for that tier, else None (prune)."""
    if hours_old < 24:
        return "hourly"
    if hours_old < 24 * 7:
        return "daily"
    if hours_old < 24 * 7 * 4:
        return "weekly"
    if hours_old < 24 * 7 * 4 * 6:
        return "monthly"
    return None


def _slot_key(ts: datetime, tier: str) -> str:
    """Return a unique key for the tier slot (e.g., 'daily-20260115')."""
    if tier == "hourly":
        return ts.strftime("%Y%m%d-%H")
    if tier == "daily":
        return ts.strftime("%Y%m%d")
    if tier == "weekly":
        return ts.strftime("%G-W%V")
    if tier == "monthly":
        return ts.strftime("%Y-%m")
    return ts.strftime("%Y%m%d-%H%M%S")


async def _list_existing_offsite() -> list[dict]:
    """Fetch existing backups from autobrain-backup /api/backups endpoint."""
    url = settings.BACKUP_OFFSITE_URL.rstrip("/") + "/api/backups"
    params = {"instance": settings.BACKUP_OFFSITE_INSTANCE} if settings.BACKUP_OFFSITE_INSTANCE else {}
    headers = {}
    if settings.BACKUP_OFFSITE_GUI_KEY:
        headers["X-Gui-Key"] = settings.BACKUP_OFFSITE_GUI_KEY
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            # Flatten hourly/daily/weekly into a single list with tier info
            all_backups = []
            for tier in ("hourly", "daily", "weekly"):
                for b in data.get(tier, []):
                    all_backups.append({"file": b["name"], "tier": tier, "timestamp": b.get("mtime"), "size": b.get("size")})
            return all_backups
        except Exception as e:
            logger.warning("offsite_list_failed", error=str(e))
            return []


async def _push_offsite(payload: bytes, filename: str) -> bool:
    """POST backup to autobrain-backup /api/backup/ingest."""
    url = settings.BACKUP_OFFSITE_URL.rstrip("/") + "/api/backup/ingest"
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


async def _delete_offsite(filename: str) -> bool:
    """DELETE a single backup from autobrain-backup."""
    url = settings.BACKUP_OFFSITE_URL.rstrip("/") + "/api/backup/delete"
    params = {"instance": settings.BACKUP_OFFSITE_INSTANCE, "name": filename} if settings.BACKUP_OFFSITE_INSTANCE else {"name": filename}
    headers = {}
    if settings.BACKUP_OFFSITE_GUI_KEY:
        headers["X-Gui-Key"] = settings.BACKUP_OFFSITE_GUI_KEY
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.delete(url, params=params, headers=headers)
            r.raise_for_status()
            logger.info("offsite_delete_ok", file=filename)
            return True
        except Exception as e:
            logger.warning("offsite_delete_failed", file=filename, error=str(e))
            return False


async def _apply_tiered_retention(existing: list[dict]) -> None:
    """Apply tiered retention (hourly/daily/weekly/monthly) to off-site backups."""
    now = datetime.now(timezone.utc)
    kept_slots = {"hourly": set(), "daily": set(), "weekly": set(), "monthly": set()}
    to_delete = []

    for b in existing:
        ts_str = b.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        hours_old = int((now - ts).total_seconds() / 3600)
        tier = _tier_for_age(hours_old)
        if tier is None:
            to_delete.append(b)
            continue
        slot = _slot_key(ts, tier)
        if slot in kept_slots[tier]:
            to_delete.append(b)
        else:
            kept_slots[tier].add(slot)

    if to_delete:
        logger.info("offsite_tiered_prune", count=len(to_delete), tiers={k: len(v) for k, v in kept_slots.items()})
        for b in to_delete:
            await _delete_offsite(b["file"])


async def run_backup_offsite() -> None:
    """Hourly task: serialize DB, push to autobrain-backup, apply tiered retention."""
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
    if ok:
        existing = await _list_existing_offsite()
        await _apply_tiered_retention(existing)

    logger.info(
        "offsite_backup_done",
        filename=filename,
        size=len(payload),
        tables=len(data.get("data") or {}),
        pushed=ok,
        duration_seconds=round(time.monotonic() - started, 3),
    )