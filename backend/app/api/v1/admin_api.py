"""Admin API-key routes (machine-to-machine).

Authenticated with the `X-Admin-API-Key` header (ADMIN_API_KEY env var).
Allows external systems to create users, set permissions (role, vehicle
quota, free/paid account, OBD access), list, disable and delete users, and
take full-database backup/restore (including MinIO image assets) for
off-box retention (autobrain-backup).
"""

import asyncio
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_api_key
from app.core.config import settings
from app.core.security import hash_password
from app.core.storage import get_minio
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AdminUserUpdate, UserAdminOut, UserCreate
from app.services import email as mail
from app.services.assets import export_assets, restore_assets
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all

router = APIRouter(prefix="/admin-api", tags=["admin-api"], dependencies=[Depends(require_admin_api_key)])


@router.get("/backup")
async def download_backup(db: AsyncSession = Depends(get_db)) -> Response:
    """Full database snapshot (JSON) for machine-to-machine off-box retention."""
    data = await serialize_all(db)
    content = dump_backup(data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autobrain-backup-{stamp}.json"'},
    )


@router.get("/assets/backup")
async def download_assets() -> StreamingResponse:
    """Tar.gz of every object in MINIO_BUCKET for off-box image retention."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = await asyncio.to_thread(export_assets, get_minio())
    with tempfile.NamedTemporaryFile(prefix="autobrain-assets-", suffix=".tar.gz", delete=False) as tmp:
        tmp.write(archive)
        tmp_path = Path(tmp.name)
    return StreamingResponse(
        _file_chunks(tmp_path),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="autobrain-assets-{stamp}.tar.gz"'},
    )


def _file_chunks(path: Path, size: int = 1 << 20):
    try:
        with path.open("rb") as f:
            while chunk := f.read(size):
                yield chunk
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@router.post("/assets/restore")
async def restore_assets_endpoint(
    file: UploadFile = File(...),
) -> dict:
    """Wipe MINIO_BUCKET and restore its objects from an uploaded tar.gz. DANGEROUS."""
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image archive too large")
    count = await asyncio.to_thread(restore_assets, get_minio(), raw)
    return {"message": "Assets restore complete", "objects": count}


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



@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    q: str | None = Query(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(User.email.ilike(like) | User.display_name.ilike(like))
    return list((await db.scalars(stmt)).all())


@router.post("/users", response_model=UserAdminOut, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    if not payload.send_invite and not payload.password:
        raise HTTPException(status_code=422, detail="Password required (or enable email invite)")
    hashed = hash_password(payload.password) if payload.password else hash_password(secrets.token_urlsafe(32))
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        hashed_password=hashed,
        role=payload.role,
        max_vehicles=payload.max_vehicles,
        free_account=payload.free_account,
        obd_enabled=payload.obd_enabled,
        pending=payload.send_invite,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    if payload.send_invite:
        token = None
        from app.core.security import create_invite_token
        token = create_invite_token(user.id, days=7)
        await mail.send_account_invite(user.email, user.display_name, token, settings.APP_BASE_URL, expiry_days=7)
    else:
        await mail.send_welcome(user.email, user.display_name, settings.APP_BASE_URL)
    return user


@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update permissions: role, vehicle quota, free/paid account, OBD access,
    active state, password."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    if "password" in updates:
        updates["hashed_password"] = hash_password(updates.pop("password"))
        updates["pending"] = False  # admin-set credential completes provisioning
        # Password change revokes every outstanding access + refresh token.
        user.token_version += 1
    for key, value in updates.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/disable", response_model=UserAdminOut)
async def disable_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    admin_count = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    )
    if user.role == "admin" and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    from app.services.backup import delete_user_complete

    await delete_user_complete(db, user.id)
