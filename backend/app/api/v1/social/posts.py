"""Post CRUD, sharing, uploads, and flag routes."""

import secrets
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.social import federation
from app.social.federation import FederationUnavailable
from app.social.media import MAX_UPLOAD_BYTES, MediaError, signed_url, upload_photo
from app.social.rate_limit import social_rate_limit, social_user_rate_limit
from app.social.models import (
    SocialBuild,
    SocialBuildFlag,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot, dumps

from app.api.v1.social._common import (
    CommentIn,
    FlagIn,
    PostCreate,
    PostUpdate,
    ReportIn,
    ShareScopeIn,
    _get_published,
    _plaintext,
    _push_outbox_safe,
    _serialize,
    _tombstone_removed_build,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post("/posts", status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    vehicle = await get_accessible_vehicle(db, payload.vehicle_id, user)
    scope = SocialShareScope(**payload.share_scope.model_dump())
    photo_keys: list[str] = []
    photos: list[SocialPhoto] = []
    if payload.photo_ids:
        photos = list(await db.scalars(
            select(SocialPhoto).where(
                SocialPhoto.id.in_(payload.photo_ids),
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.build_id.is_(None),
                SocialPhoto.issue_id.is_(None),
            )
        ))
        photo_keys = [p.file_key for p in photos]
    snapshot = await build_snapshot(db, vehicle, scope, photo_keys)
    cfg = await get_server_config(db)
    build = SocialBuild(
        vehicle_id=vehicle.id,
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        title=payload.title.strip() if payload.title and payload.title.strip() else snapshot["title"],
        caption=payload.caption,
        origin="local",
        snapshot_json=dumps(snapshot),
    )
    db.add(build)
    await db.flush()
    scope.build_id = build.id
    db.add(scope)
    for photo in photos:
        photo.build_id = build.id
    if build.origin == "local":
        await add_event(
            db, vehicle.id, "mod", f"Shared build: {build.title}",
            date.today(), None, None, build.id,
        )
    await db.commit()
    if build.origin == "local" and cfg.federation_enabled and cfg.hub_status == "registered":
        await _push_outbox_safe(cfg, build, snapshot, photo_keys)
    return await _serialize(db, build, user)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, post_id)
    return await _serialize(db, build, user)


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: str,
    payload: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    """Edit a build (AUT-675): name/title, caption, photo reorder/upload/remove
    and share scope. Ownership check matches delete: 404 for non-owners so
    posts cannot be probed (PW-8)."""
    build = await _get_published(db, post_id)
    if build.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    if build.origin == "remote":
        raise HTTPException(
            status_code=400, detail="Remote builds can only be edited on their origin server"
        )
    fields = payload.model_fields_set
    if "title" in fields:
        build.title = payload.title.strip() if payload.title and payload.title.strip() else build.title
    if "caption" in fields:
        build.caption = payload.caption or None
    scope = await db.scalar(
        select(SocialShareScope).where(SocialShareScope.build_id == build.id)
    )
    if "share_scope" in fields and payload.share_scope is not None:
        if scope is None:
            scope = SocialShareScope(
                build_id=build.id, **payload.share_scope.model_dump())
            db.add(scope)
        else:
            for key, value in payload.share_scope.model_dump().items():
                setattr(scope, key, value)
    if "photo_ids" in fields and payload.photo_ids is not None:
        if len(payload.photo_ids) > 12 or len(set(payload.photo_ids)) != len(payload.photo_ids):
            raise HTTPException(status_code=400, detail="Invalid photo list")
        photos = list(await db.scalars(
            select(SocialPhoto).where(
                SocialPhoto.id.in_(payload.photo_ids),
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.issue_id.is_(None),
                or_(SocialPhoto.build_id.is_(None), SocialPhoto.build_id == build.id),
            )
        ))
        by_id = {p.id: p for p in photos}
        if len(by_id) != len(payload.photo_ids):
            raise HTTPException(
                status_code=400, detail="Some photos could not be used")
        keep = set(payload.photo_ids)
        current = list(await db.scalars(
            select(SocialPhoto).where(SocialPhoto.build_id == build.id)))
        for photo in current:
            if photo.id not in keep:
                photo.build_id = None  # back to the user's unassigned pool
        for position, photo_id in enumerate(payload.photo_ids):
            photo = by_id[photo_id]
            photo.build_id = build.id
            photo.position = position
    snapshot = None
    photo_keys = []
    if build.vehicle_id:
        vehicle = await db.get(Vehicle, build.vehicle_id)
        if vehicle:
            photos = list(await db.scalars(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.position, SocialPhoto.created_at)
            ))
            snapshot = await build_snapshot(db, vehicle, scope, [p.file_key for p in photos])
            build.snapshot_json = dumps(snapshot)
            photo_keys = [p.file_key for p in photos]
    cfg = await get_server_config(db)
    await db.commit()
    if build.origin == "local" and cfg.federation_enabled and cfg.hub_status == "registered":
        await _push_outbox_safe(cfg, build, snapshot, photo_keys)
    return await _serialize(db, build, user)


@router.post("/posts/{post_id}/share-link")
async def create_share_link(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    build = await _get_published(db, post_id)
    if build.origin == "remote":
        raise HTTPException(
            status_code=400,
            detail="Share links for remote builds resolve on their origin server",
        )
    if not build.share_token:
        build.share_token = secrets.token_urlsafe(16)
        await db.commit()
    return {"token": build.share_token, "url": f"/social/share/{build.share_token}"}


@router.get("/share/{token}")
async def resolve_share_link(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await db.scalar(select(SocialBuild).where(SocialBuild.share_token == token))
    if not build or build.status != "published":
        raise HTTPException(status_code=404, detail="Build not found")
    return await _serialize(db, build, user)


def _reject_oversized_content_length(request: Request) -> None:
    """Return 413 on a declared Content-Length past the cap before any body read.

    Must resolve before the UploadFile dependency so the multipart body is never
    parsed/buffered for oversized uploads. Missing or lying Content-Length is
    covered by the bounded read_upload() inside the handler.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")


@router.post("/uploads", status_code=201)
async def upload(
    _size_guard: None = Depends(_reject_oversized_content_length),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    from app.api.v1.social import read_upload
    try:
        data = await read_upload(file)
        key, url, width, height = await upload_photo(user.id, data, file.content_type)
    except MediaError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    photo = SocialPhoto(uploader_user_id=user.id, file_key=key, width=width, height=height)
    db.add(photo)
    await db.commit()
    return {"id": photo.id, "url": url}


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> None:
    """Unshare a build (takedown propagates via the hub).

    Authors may unshare their own builds; admins may remove any build on their
    server (local or federated copy) directly from the community pages
    (AUT-902). Non-owners get a 404, not a 403, so they cannot tell a post
    exists (PW-8).
    """
    build = await _get_published(db, post_id)
    is_author = build.author_user_id == user.id
    if not is_author and user.role != "admin":
        raise HTTPException(status_code=404, detail="Post not found")
    origin = build.origin
    await _tombstone_removed_build(db, build)
    # Bulk deletes/update run immediately, so every child row is gone before the
    # parent DELETE — an ORM db.delete loop does not order child deletes first
    # (no relationship/cascade) and 500s on the FK (AUT-703, AUT-762).
    await db.execute(
        update(SocialPhoto)
        .where(SocialPhoto.build_id == build.id)
        .values(build_id=None)
    )
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id))
    await db.delete(build)
    await db.commit()
    # Takedown fan-out for locally-hosted posts only; a federated copy's
    # origin is another server, so removing the local copy stays local.
    if origin == "local":
        cfg = await get_server_config(db)
        if cfg.federation_enabled and cfg.hub_status == "registered" and cfg.hub_server_id:
            try:
                await federation.push_removed(cfg, str(build.id), "build")
            except (FederationUnavailable, Exception) as exc:
                logger.warning("social_remove_push_failed", build_id=build.id, error=str(exc))


@router.post("/posts/{post_id}/flag", status_code=201)
async def flag_build(
    post_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("builds-flag", 5)),
) -> dict:
    """Report a build post (AUT-883 moderation queue). Deduped per user."""
    build = await _get_published(db, post_id)
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialBuildFlag).where(
            SocialBuildFlag.build_id == build.id,
            SocialBuildFlag.flagged_by_user_id == user.id,
            SocialBuildFlag.comment_id.is_(None),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this post")
    db.add(SocialBuildFlag(
        build_id=build.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}


@router.post("/posts/{post_id}/comments/{comment_id}/flag", status_code=201)
async def flag_build_comment(
    post_id: str,
    comment_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("builds-flag-comment", 5)),
) -> dict:
    """Report a comment on a build (AUT-883 moderation queue)."""
    build = await _get_published(db, post_id)
    comment = await db.get(SocialComment, comment_id)
    if not comment or comment.build_id != build.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialBuildFlag).where(
            SocialBuildFlag.comment_id == comment.id,
            SocialBuildFlag.flagged_by_user_id == user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this comment")
    db.add(SocialBuildFlag(
        build_id=build.id,
        comment_id=comment.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}