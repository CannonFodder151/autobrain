"""Admin user management routes (admin role only)."""

import secrets

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_invite_token, hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AdminUserUpdate, UserAdminOut, UserCreate, UserPage
from app.services import email as mail
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])

# --- server ops (version, backups) ---
admin_ops = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@admin_ops.get("/version")
async def server_version() -> dict:
    """Current server version (local only — no GitHub update check)."""
    return {"version": settings.APP_VERSION}


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



@router.get("", response_model=UserPage)
async def list_users(
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
) -> UserPage:
    """Search users by display name or email, alphabetical, 15 per page."""
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(User.email.ilike(like) | User.display_name.ilike(like))
    total = (await db.scalar(
        select(func.count()).select_from(stmt.subquery())
    )) or 0
    rows = list((await db.scalars(
        stmt.order_by(User.display_name.asc()).offset((page - 1) * 15).limit(15)
    )).all())
    return UserPage(
        items=rows, total=total, page=page,
        pages=max((total + 14) // 15, 1),
    )


@router.post("", response_model=UserAdminOut, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    name_taken = await db.scalar(
        select(User).where(func.lower(User.display_name) == payload.display_name.lower())
    )
    if name_taken:
        raise HTTPException(status_code=409, detail="Display name already in use")
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
        updates["pending"] = False  # admin-set credential completes provisioning
        # Password change revokes every outstanding access + refresh token.
        user.token_version += 1
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


# --- Community Garage admin toggles (AUT-332) ---


class _SocialConfigUpdate(BaseModel):
    feature_enabled: bool | None = None
    federation_enabled: bool | None = None
    server_name: str | None = None
    server_email: str | None = None


@admin_ops.get("/social")
async def social_config(db: AsyncSession = Depends(get_db)) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    return {
        "feature_enabled": cfg.feature_enabled,
        "federation_enabled": cfg.federation_enabled,
        "server_name": cfg.server_name,
        "server_email": cfg.server_email,
        "hub_status": cfg.hub_status,
        "hub_server_id": cfg.hub_server_id,
        "hub_url": cfg.server_hub_url or settings.SOCIAL_FEDERATION_HUB_URL,
    }


@admin_ops.patch("/social")
async def update_social_config(
    payload: _SocialConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)
    return {"message": "Community Garage settings updated", "feature_enabled": cfg.feature_enabled}


@admin_ops.post("/social/register")
async def register_social_server(db: AsyncSession = Depends(get_db)) -> dict:
    """Register this server with the federation hub (req 14)."""
    from app.social import federation as fed
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    if not cfg.server_name or not cfg.server_email:
        raise HTTPException(
            status_code=400,
            detail="Set server_name and server_email first (PATCH /admin/social)",
        )
    # AUT-758: the server keypair is generated once and reused on every
    # (re)registration attempt — it must not rotate while trying to join.
    if cfg.hub_private_key:
        private_key = cfg.hub_private_key
        public_key = fed.public_key_from_private(private_key)
    else:
        private_key, public_key = fed.generate_keypair()
        cfg.hub_private_key = private_key
    try:
        result = await fed.register(cfg, cfg.server_name, cfg.server_email, public_key)
    except fed.FederationUnavailable as exc:
        cfg.hub_status = "error"
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Hub unreachable: {exc}")
    cfg.hub_status = "registered" if result.get("status") in ("approved", "registered") else "pending"
    cfg.hub_server_id = str(result.get("server_id"))
    cfg.hub_api_key = str(result.get("api_key"))
    cfg.hub_private_key = private_key
    await db.commit()
    return {
        "hub_status": cfg.hub_status,
        "hub_server_id": cfg.hub_server_id,
        "server_name": cfg.server_name,
        "license_status": result.get("license_status"),
    }


@admin_ops.post("/social/unregister")
async def unregister_social_server(db: AsyncSession = Depends(get_db)) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    cfg.hub_status = "unregistered"
    cfg.hub_server_id = None
    cfg.hub_api_key = None
    cfg.hub_private_key = None
    await db.commit()
    return {"message": "Server removed from the federation hub", "hub_status": cfg.hub_status}


# --- Issues Blog moderation (AUT-627) ---


class _IssueModerationUpdate(BaseModel):
    status_hidden: bool | None = None
    status: str | None = None


@admin_ops.get("/issues/flagged")
async def flagged_issues(db: AsyncSession = Depends(get_db)) -> dict:
    """Moderation queue: every flagged issue post with its flag count."""
    from app.social.models import SocialIssueFlag, SocialIssuePost

    rows = await db.execute(
        select(
            SocialIssuePost.id,
            SocialIssuePost.title,
            SocialIssuePost.status,
            SocialIssuePost.status_hidden,
            SocialIssuePost.author_user_id,
            SocialIssuePost.author_display_name,
            SocialIssuePost.created_at,
            func.count(SocialIssueFlag.id).label("flag_count"),
        )
        .join(SocialIssueFlag, SocialIssueFlag.post_id == SocialIssuePost.id)
        .where(SocialIssueFlag.comment_id.is_(None))
        .group_by(SocialIssuePost.id)
        .order_by(func.count(SocialIssueFlag.id).desc())
    )
    return {
        "items": [
            {
                "kind": "post",
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "status_hidden": r.status_hidden,
                "author_user_id": r.author_user_id,
                "author_display_name": r.author_display_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "flag_count": r.flag_count,
            }
            for r in rows
        ]
    }


@admin_ops.get("/issues/review")
async def review_queue(db: AsyncSession = Depends(get_db)) -> dict:
    """Unified moderation hub (AUT-832 + AUT-883): every flagged issue OR build
    post/comment with the reporting reasons and author info, newest report
    first. `target` distinguishes issue entries from build entries so the hub
    can route deletes to the right admin endpoint."""
    from app.social.models import (
        SocialBuild,
        SocialBuildFlag,
        SocialComment,
        SocialIssueComment,
        SocialIssueFlag,
        SocialIssuePost,
    )

    items: list[dict] = []

    stmt = (
        select(
            SocialIssueFlag.id.label("flag_id"),
            SocialIssueFlag.reason,
            SocialIssueFlag.created_at.label("flagged_at"),
            SocialIssuePost.id.label("post_id"),
            SocialIssuePost.title.label("post_title"),
            SocialIssuePost.status_hidden,
            SocialIssuePost.author_user_id.label("post_author_id"),
            SocialIssuePost.author_display_name.label("post_author_name"),
            SocialIssueComment.id.label("comment_id"),
            SocialIssueComment.author_user_id.label("comment_author_id"),
            SocialIssueComment.author_display_name.label("comment_author_name"),
            SocialIssueComment.body.label("comment_body"),
        )
        .join(SocialIssuePost, SocialIssuePost.id == SocialIssueFlag.post_id)
        .outerjoin(SocialIssueComment, SocialIssueComment.id == SocialIssueFlag.comment_id)
        .order_by(SocialIssueFlag.created_at.desc())
        .limit(200)
    )
    for r in (await db.execute(stmt)).all():
        items.append({
            "flag_id": r.flag_id,
            "reason": r.reason,
            "flagged_at": r.flagged_at.isoformat() if r.flagged_at else None,
            "target": "issue",
            "kind": "comment" if r.comment_id else "post",
            "post_id": r.post_id,
            "post_title": r.post_title,
            "post_hidden": r.status_hidden,
            "post_author_user_id": r.post_author_id,
            "post_author_display_name": r.post_author_name,
            "comment_id": r.comment_id,
            "comment_body": r.comment_body,
            "comment_author_user_id": r.comment_author_id,
            "comment_author_display_name": r.comment_author_name,
        })

    build_stmt = (
        select(
            SocialBuildFlag.id.label("flag_id"),
            SocialBuildFlag.reason,
            SocialBuildFlag.created_at.label("flagged_at"),
            SocialBuild.id.label("post_id"),
            SocialBuild.title.label("post_title"),
            SocialBuild.status.label("build_status"),
            SocialBuild.author_user_id.label("post_author_id"),
            SocialBuild.author_display_name.label("post_author_name"),
            SocialComment.id.label("comment_id"),
            SocialComment.author_user_id.label("comment_author_id"),
            SocialComment.author_display_name.label("comment_author_name"),
            SocialComment.body.label("comment_body"),
        )
        .join(SocialBuild, SocialBuild.id == SocialBuildFlag.build_id)
        .outerjoin(SocialComment, SocialComment.id == SocialBuildFlag.comment_id)
        .order_by(SocialBuildFlag.created_at.desc())
        .limit(200)
    )
    for r in (await db.execute(build_stmt)).all():
        items.append({
            "flag_id": r.flag_id,
            "reason": r.reason,
            "flagged_at": r.flagged_at.isoformat() if r.flagged_at else None,
            "target": "build",
            "kind": "comment" if r.comment_id else "post",
            "post_id": r.post_id,
            "post_title": r.post_title,
            "post_hidden": r.build_status != "published",
            "post_author_user_id": r.post_author_id,
            "post_author_display_name": r.post_author_name,
            "comment_id": r.comment_id,
            "comment_body": r.comment_body,
            "comment_author_user_id": r.comment_author_id,
            "comment_author_display_name": r.comment_author_name,
        })

    items.sort(key=lambda i: i["flagged_at"] or "", reverse=True)
    return {"items": items[:200]}


@admin_ops.delete("/issues/comments/{comment_id}", status_code=204)
async def delete_comment_admin(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a single issue comment (moderation hub, AUT-832)."""
    from sqlalchemy import delete

    from app.social.models import SocialIssueComment, SocialIssueFlag, SocialIssuePost, SocialPhoto

    comment = await db.get(SocialIssueComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    photo_keys = list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.comment_id == comment.id)
    ))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id == comment.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.comment_id == comment.id))
    if comment.is_answer:
        post = await db.get(SocialIssuePost, comment.post_id)
        if post:
            post.resolved_comment_id = None
            if post.status == "resolved":
                post.status = "open"
    await db.delete(comment)
    await db.commit()
    await _best_effort_delete_media(photo_keys)


@admin_ops.delete("/issues/posts/{issue_id}", status_code=204)
async def delete_issue_admin(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes an issue post outright (moderation hub, AUT-832)."""
    from sqlalchemy import delete

    from app.social.models import SocialIssueComment, SocialIssueFlag, SocialIssuePost, SocialPhoto

    post = await db.get(SocialIssuePost, issue_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comment_ids = list(await db.scalars(
        select(SocialIssueComment.id).where(SocialIssueComment.post_id == post.id)
    ))
    media_keys: list[str] = []
    if comment_ids:
        media_keys += list(await db.scalars(
            select(SocialPhoto.file_key).where(SocialPhoto.comment_id.in_(comment_ids))
        ))
        await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id.in_(comment_ids)))
    media_keys += list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.issue_id == post.id)
    ))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.issue_id == post.id))
    await db.execute(delete(SocialIssueComment).where(SocialIssueComment.post_id == post.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.post_id == post.id))
    await db.delete(post)
    await db.commit()
    await _best_effort_delete_media(media_keys)


@admin_ops.delete("/social/comments/{comment_id}", status_code=204)
async def delete_build_comment_admin(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a single build comment (moderation hub, AUT-883)."""
    from sqlalchemy import delete

    from app.social.models import SocialBuildFlag, SocialComment

    comment = await db.get(SocialComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.comment_id == comment.id))
    await db.delete(comment)
    await db.commit()


@admin_ops.delete("/social/posts/{build_id}", status_code=204)
async def delete_build_admin(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a build post outright (moderation hub, AUT-883):
    cascades comments, likes, share scope and flags, best-effort MinIO purge."""
    from sqlalchemy import delete, update

    from app.social.models import (
        SocialBuild,
        SocialBuildFlag,
        SocialComment,
        SocialLike,
        SocialPhoto,
        SocialShareScope,
    )

    build = await db.get(SocialBuild, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")
    media_keys = list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.build_id == build.id)
    ))
    await db.execute(update(SocialPhoto).where(SocialPhoto.build_id == build.id).values(build_id=None))
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id))
    await db.delete(build)
    await db.commit()
    await _best_effort_delete_media(media_keys)


async def _best_effort_delete_media(file_keys: list[str]) -> None:
    """Best-effort MinIO cleanup on admin takedowns (AUT-832 F4). Object removal
    must never fail a moderation delete, so any storage error is swallowed."""
    if not file_keys:
        return
    try:
        from app.core.storage import delete_object

        for key in file_keys:
            await delete_object(key)
    except Exception:
        return


@admin_ops.post("/users/{user_id}/social-ban")
async def social_ban_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Ban a user from posting in Community Garage and hide all their issue
    posts (moderation hub, AUT-832). Unban restores only what the ban hid —
    posts an admin hid separately stay hidden.

    Scope note: the ban gates every social write (incl. replies/builds) but
    only *hides* issue posts; comments and build posts are removed via the
    hub's per-item delete actions instead (intended, AUT-832 F5)."""
    from sqlalchemy import update

    from app.social.models import SocialIssuePost

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == _admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban your own account")
    user.social_banned = True
    await db.execute(
        update(SocialIssuePost)
        .where(
            SocialIssuePost.author_user_id == user.id,
            SocialIssuePost.status_hidden.is_(False),
        )
        .values(status_hidden=True, hidden_by_ban=True)
    )
    await db.commit()
    return {"message": f"{user.display_name} banned from posting", "social_banned": True}


@admin_ops.post("/users/{user_id}/social-unban")
async def social_unban_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Reverse a social ban, restoring only the posts the ban itself hid."""
    from sqlalchemy import update

    from app.social.models import SocialIssuePost

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.social_banned = False
    await db.execute(
        update(SocialIssuePost)
        .where(
            SocialIssuePost.author_user_id == user.id,
            SocialIssuePost.hidden_by_ban.is_(True),
        )
        .values(status_hidden=False, hidden_by_ban=False)
    )
    await db.commit()
    return {"message": f"{user.display_name} unbanned", "social_banned": False}


@admin_ops.patch("/issues/{issue_id}")
async def moderate_issue(
    issue_id: str,
    payload: _IssueModerationUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hide/restore an issue post and optionally change its status."""
    from app.api.v1.issues import ISSUE_STATUSES
    from app.social.models import SocialIssuePost

    post = await db.get(SocialIssuePost, issue_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if payload.status_hidden is not None:
        post.status_hidden = payload.status_hidden
    if payload.status is not None:
        if payload.status not in ISSUE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        post.status = payload.status
    await db.commit()
    return {
        "message": "Issue post updated",
        "id": post.id,
        "status_hidden": post.status_hidden,
        "status": post.status,
    }
