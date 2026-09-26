"""Admin API-key routes (machine-to-machine).

Authenticated with the `X-Admin-API-Key` header (ADMIN_API_KEY env var).
Allows external systems to create users, set permissions (role, vehicle
quota, free/paid account, OBD access), list, disable and delete users, and
take full-database backup/restore (including MinIO image assets) for
off-box retention (autobrain-backup).

SECURITY: Restore endpoints require a confirmation token. Tokens are
single-use, 5-minute TTL, generated via POST /admin-api/confirm-token.
All restore actions are logged to admin_audit.log. (AUT-3082)
"""

import asyncio
import hashlib
import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile
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
from app.services.assets import export_assets, restore_assets, restore_assets_file
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all

router = APIRouter(prefix="/admin-api", tags=["admin-api"], dependencies=[Depends(require_admin_api_key)])

# In-memory confirmation token store (single-process uvicorn).
# Token format: {token_hash: (created_at, description)}
_confirm_tokens: dict[str, tuple[float, str]] = {}
_TOKEN_TTL_SECONDS = 300  # 5 minutes
_AUDIT_LOG_PATH = Path("admin_audit.log")


def _issue_confirmation_token(description: str) -> str:
    """Issue a short-lived single-use confirmation token."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _confirm_tokens[token_hash] = (time.time(), description)
    return token


def _consume_confirmation_token(token: str | None, description: str) -> None:
    """Validate and consume a confirmation token. Raises 403 on invalid."""
    if not token:
        raise HTTPException(status_code=403, detail="Confirmation token required. POST /admin-api/confirm-token first.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    entry = _confirm_tokens.pop(token_hash, None)
    if entry is None:
        raise HTTPException(status_code=403, detail="Invalid or expired confirmation token.")
    created_at, desc = entry
    if time.time() - created_at > _TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="Confirmation token expired.")
    if desc != description:
        raise HTTPException(status_code=403, detail=f"Token issued for '{desc}', not '{description}'.")
    _audit_log(description, "executed")


def _audit_log(action: str, result: str, detail: str = "") -> None:
    """Append an audit entry to admin_audit.log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "result": result,
        "detail": detail,
    }
    try:
        with _AUDIT_LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # best-effort; don't fail the request over logging


@router.post("/confirm-token")
async def issue_confirmation_token(
    description: str = Query(..., max_length=255, description="What the token authorizes (e.g. 'restore-db', 'restore-assets')"),
) -> dict:
    """Issue a single-use 5-minute confirmation token for a destructive action."""
    token = _issue_confirmation_token(description)
    _audit_log(f"confirm-token:{description}", "issued")
    return {"token": token, "expires_in": _TOKEN_TTL_SECONDS, "description": description}


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
    x_confirm_token: str | None = Header(default=None, alias="X-Confirm-Token"),
) -> dict:
    """Wipe MINIO_BUCKET and restore its objects from an uploaded tar.gz. DANGEROUS.

    Requires a valid confirmation token from POST /admin-api/confirm-token?description=restore-assets.
    Streams the upload to a temp file (1 GB cap) to avoid OOM on large archives.
    """
    _consume_confirmation_token(x_confirm_token, "restore-assets")
    max_size = 1 * 1024 * 1024 * 1024  # 1 GB
    total = 0
    with tempfile.NamedTemporaryFile(prefix="autobrain-assets-", suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name
        try:
            while chunk := await file.read(1 << 20):  # 1 MB chunks
                total += len(chunk)
                if total > max_size:
                    raise HTTPException(status_code=413, detail="Image archive too large (max 1 GB)")
                tmp.write(chunk)
        except HTTPException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise HTTPException(status_code=400, detail="Failed to save upload")
    try:
        count = await asyncio.to_thread(restore_assets_file, get_minio(), tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    _audit_log("restore-assets", "executed", f"objects={count}")
    return {"message": "Assets restore complete", "objects": count}


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    x_confirm_token: str | None = Header(default=None, alias="X-Confirm-Token"),
) -> dict:
    """Wipe and restore the whole database from an uploaded backup. DANGEROUS.

    Requires a valid confirmation token from POST /admin-api/confirm-token?description=restore-db.
    """
    _consume_confirmation_token(x_confirm_token, "restore-db")
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup file too large")
    try:
        data = load_backup(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await restore_all(db, data)
    _audit_log("restore-db", "executed", f"restored_at={data.get('created_at')}")
    return {"message": "Restore complete", "restored_at": data.get("created_at")}



def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/users", response_model=list[UserAdminOut])
async def list_users(
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1, description="Page number (15 per page)"),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{_escape_ilike(q.lower())}%"
        stmt = stmt.where(User.email.ilike(like, escape="\\") | User.display_name.ilike(like, escape="\\"))
    return list((await db.scalars(stmt.offset((page - 1) * 15).limit(15))).all())


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
