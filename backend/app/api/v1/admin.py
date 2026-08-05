"""Admin user management routes (admin role only)."""

import secrets

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_invite_token, hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AdminUserUpdate, UserAdminOut, UserCreate
from app.services import email as mail
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all
from app.services.version import check_latest_release, current_version

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])

# --- server ops (version, backups) ---
admin_ops = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@admin_ops.get("/version")
async def server_version() -> dict:
    """Current server version + GitHub latest-release check."""
    version = current_version()
    release = await check_latest_release()
    return {
        "version": version,
        "repo": settings.GITHUB_REPO,
        **release,
        "up_to_date": release["up_to_date"] if release.get("up_to_date") is not None else None,
    }


@admin_ops.get("/backup")
async def download_backup(db: AsyncSession = Depends(get_db)) -> Response:
    """Full database snapshot (JSON). Download and keep off-box."""
    data = await serialize_all(db)
    content = dump_backup(data)
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autobrain-backup-{stamp}.json"'},
    )


@admin_ops.post("/restore")
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



@router.get("", response_model=list[UserAdminOut])
async def list_users(
    q: str | None = Query(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            User.email.ilike(like) | User.display_name.ilike(like)
        )
    return list((await db.scalars(stmt)).all())


@router.post("", response_model=UserAdminOut, status_code=201)
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
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    if payload.send_invite:
        token = create_invite_token(user.id, days=7)
        await mail.send_account_invite(user.email, user.display_name, token, settings.APP_BASE_URL, expiry_days=7)
    else:
        await mail.send_welcome(user.email, user.display_name, settings.APP_BASE_URL)
    return user


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    if "password" in updates:
        updates["hashed_password"] = hash_password(updates.pop("password"))
    for key, value in updates.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/re-upgrade", response_model=UserAdminOut)
async def re_upgrade_user(
    user_id: str,
    enabled: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Grant (or revoke, with enabled=false) the $19/month Enthusiast benefits
    without a Stripe subscription. Re-upgraded accounts are blocked from
    buying a licence (see billing.create_checkout_session)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if enabled:
        user.free_account = False
        user.max_vehicles = 1
    else:
        user.free_account = True
        user.max_vehicles = 1
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == _admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    admin_count = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    )
    if user.role == "admin" and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    from app.services.backup import delete_user_complete

    await delete_user_complete(db, user.id)


@router.get("/{user_id}/backup")
async def backup_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download a single user's profile (all their vehicles + records)."""
    from app.services.backup import dump_backup, serialize_user

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = await serialize_user(db, user_id)
    content = dump_backup(data)
    stamp = user.email.split("@")[0].replace(".", "-")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autobrain-user-{stamp}.json"'},
    )


@router.post("/{user_id}/restore")
async def restore_user(
    user_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Restore/override a user's data from an uploaded profile export."""
    import json as _json

    from app.services.backup import restore_user_data

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    try:
        data = _json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Not a valid AutoBrain export file")
    if data.get("app") != "autobrain" or data.get("kind") != "profile":
        raise HTTPException(status_code=400, detail="Not an AutoBrain profile export file")
    try:
        await restore_user_data(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": f"User {user.email} restored"}
