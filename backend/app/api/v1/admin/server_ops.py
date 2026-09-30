"""Admin server operations (version, whole-database backup/restore)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/version")
async def server_version() -> dict:
    """Current server version (local only — no GitHub update check)."""
    return {"version": settings.APP_VERSION}


@router.get("/backup")
async def download_backup(db: AsyncSession = Depends(get_db)) -> Response:
    """Full database snapshot (JSON). Download and keep off-box."""
    data = await serialize_all(db)
    content = dump_backup(data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autobrain-backup-{stamp}.json"'},
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Wipe and restore the whole database from an uploaded backup. DANGEROUS."""
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup file too large")
    try:
        data = load_backup(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await restore_all(db, data)
    return {"message": "Restore complete", "restored_at": data.get("created_at")}
