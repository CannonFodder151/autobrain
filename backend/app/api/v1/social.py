"""Community Garage social routes (AUT-294 rev 7, AUT-332).

Feature gate: every route 403s with "Disabled by your admin" when the feature
toggle is off, and requires premium entitlement (rev 4). Federation off = the
feed still works, local builds only.
"""

import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
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
from app.social.media import MediaError, signed_url, upload_photo
from app.social.models import (
    SocialBuild,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot, dumps, loads

logger = get_logger(__name__)

_INBOX_SYNC_TTL_SECONDS = 60


async def require_social_feature(db: AsyncSession = Depends(get_db)) -> None:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        raise HTTPException(status_code=403, detail="Disabled by your admin")


router = APIRouter(
    prefix="/social",
    tags=["social"],
    dependencies=[Depends(require_social_feature)],
)


class ShareScopeIn(BaseModel):
    allow_photos: bool = True
    allow_specs: bool = True
    allow_mods: bool = True
    allow_odometer: bool = False
    allow_notes: bool = False


class PostCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=36)
    caption: str | None = Field(default=None, max_length=1000)
    share_scope: ShareScopeIn = ShareScopeIn()
    photo_ids: list[str] = Field(default_factory=list, max_length=12)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


async def _like_count(db: AsyncSession, build_id: str) -> int:
    return (await db.scalar(
        select(func.count()).select_from(SocialLike).where(SocialLike.build_id == build_id)
    )) or 0


async def _comment_count(db: AsyncSession, build_id: str) -> int:
    return (await db.scalar(
        select(func.count()).select_from(SocialComment).where(SocialComment.build_id == build_id)
    )) or 0


async def _serialize(db: AsyncSession, build: SocialBuild, viewer: User | None) -> dict:
    snapshot = loads(build.snapshot_json)
    photo_keys = list(snapshot.get("photo_keys", []))
    if build.origin in ("local", "demo") and build.vehicle_id:
        vehicle = await db.get(Vehicle, build.vehicle_id)
        if vehicle:
            scope = await db.scalar(
                select(SocialShareScope).where(SocialShareScope.build_id == build.id)
            )
            photos = list(await db.scalars(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.created_at)
            ))
            snapshot = await build_snapshot(db, vehicle, scope, [p.file_key for p in photos])
            photo_keys = list(snapshot.get("photo_keys", []))
    photos: list[str] = []
    for key in photo_keys:
        try:
            photos.append(await signed_url(key))
        except Exception:
            continue
    liked = viewer is not None and (
        await db.scalar(
            select(SocialLike).where(
                SocialLike.build_id == build.id,
                SocialLike.author_user_id == viewer.id,
            )
        )
    ) is not None
    return {
        "id": build.id,
        "title": build.title,
        "caption": build.caption,
        "author_display_name": build.remote_author_display_name or build.author_display_name,
        "server_name": build.server_name,
        "origin": build.origin,
        "snapshot": snapshot,
        "photos": photos,
        "like_count": await _like_count(db, build.id),
        "liked_by_me": liked,
        "comment_count": await _comment_count(db, build.id),
        "created_at": build.created_at.isoformat(),
    }


async def _get_published(db: AsyncSession, build_id: str) -> SocialBuild:
    build = await db.get(SocialBuild, build_id)
    if not build or build.status != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    return build


async def _sync_inbox(db: AsyncSession) -> None:
    """Pull remote builds from the hub when due. Errors never break the feed."""
    cfg = await get_server_config(db)
    if not cfg.federation_enabled or cfg.hub_status != "registered" or not cfg.hub_server_id:
        return
    if cfg.last_inbox_sync and (
        datetime.now(timezone.utc) - cfg.last_inbox_sync < timedelta(seconds=_INBOX_SYNC_TTL_SECONDS)
    ):
        return
    try:
        remote_builds = await federation.pull_inbox(cfg)
    except FederationUnavailable as exc:
        logger.warning("social_inbox_sync_failed", error=str(exc))
        return
    for item in remote_builds:
        build = item.get("build") or item
        rid = build.get("remote_build_id") or build.get("build_id")
        if not rid:
            continue
        existing = await db.scalar(
            select(SocialBuild).where(SocialBuild.remote_build_id == str(rid))
        )
        if existing:
            continue
        db.add(SocialBuild(
            author_display_name=build.get("author_display_name", "Unknown"),
            remote_author_display_name=build.get("author_display_name"),
            server_name=build.get("server_name"),
            title=build.get("title", "Untitled build"),
            caption=build.get("caption"),
            origin="remote",
            remote_build_id=str(rid),
            remote_server_id=item.get("origin_server") or build.get("server_id"),
            snapshot_json=dumps(build.get("snapshot") or {}),
        ))
    cfg.last_inbox_sync = datetime.now(timezone.utc)
    await db.flush()


async def _push_outbox_safe(cfg, build_id: str, snapshot: dict, photo_keys: list[str]) -> None:
    try:
        await federation.push_outbox(cfg, build_id, {
            "build_id": build_id,
            "title": snapshot.get("title"),
            "snapshot": snapshot,
            "photo_urls": [await signed_url(k) for k in photo_keys],
        })
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_outbox_push_failed", build_id=build_id, error=str(exc))


@router.get("/feed")
async def feed(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    await _sync_inbox(db)
    await db.commit()
    rows = await db.scalars(
        select(SocialBuild)
        .where(SocialBuild.status == "published")
        .order_by(SocialBuild.created_at.desc())
        .limit(limit)
    )
    return {"items": [await _serialize(db, b, user) for b in rows]}


@router.post("/posts", status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
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
        title=snapshot["title"],
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
        await _push_outbox_safe(cfg, build.id, snapshot, photo_keys)
    return await _serialize(db, build, user)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, post_id)
    return await _serialize(db, build, user)


@router.post("/posts/{post_id}/comments", status_code=201)
async def add_comment(
    post_id: str,
    payload: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, post_id)
    cfg = await get_server_config(db)
    comment = SocialComment(
        build_id=build.id,
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        body=payload.body,
    )
    db.add(comment)
    await db.commit()
    if build.origin == "remote":
        await _push_event_safe(db, build, "comment", {"body": payload.body})
    return {
        "id": comment.id,
        "build_id": build.id,
        "author_display_name": comment.author_display_name,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
    }


@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, post_id)
    rows = await db.scalars(
        select(SocialComment).where(SocialComment.build_id == build.id).order_by(SocialComment.created_at)
    )
    return {
        "items": [
            {
                "id": c.id,
                "author_display_name": c.author_display_name,
                "server_name": c.server_name,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]
    }


@router.post("/posts/{post_id}/likes")
async def toggle_like(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, post_id)
    cfg = await get_server_config(db)
    existing = await db.scalar(
        select(SocialLike).where(
            SocialLike.build_id == build.id,
            SocialLike.author_user_id == user.id,
        )
    )
    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(SocialLike(
            build_id=build.id,
            author_user_id=user.id,
            author_display_name=user.display_name,
            server_name=cfg.server_name,
        ))
        liked = True
    await db.commit()
    if build.origin == "remote":
        await _push_event_safe(db, build, "like", {"liked": liked})
    return {"liked": liked, "like_count": await _like_count(db, build.id)}


@router.get("/posts/{post_id}/likes")
async def list_likes(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, post_id)
    rows = await db.scalars(
        select(SocialLike).where(SocialLike.build_id == build.id).order_by(SocialLike.created_at.desc())
    )
    return {
        "items": [
            {
                "id": like.id,
                "author_display_name": like.author_display_name,
                "server_name": like.server_name,
                "created_at": like.created_at.isoformat(),
            }
            for like in rows
        ]
    }


async def _push_event_safe(db: AsyncSession, build: SocialBuild, kind: str, payload: dict) -> None:
    cfg = await get_server_config(db)
    try:
        await federation.push_outbox(cfg, build.id, {"event": kind, **payload})
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_event_push_failed", kind=kind, build_id=build.id, error=str(exc))


@router.post("/posts/{post_id}/share-link")
async def create_share_link(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium_write),
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

@router.post("/uploads", status_code=201)
async def upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    data = await file.read()
    try:
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
    """Unshare a build (takedown propagates locally)."""
    build = await _get_published(db, post_id)
    if build.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the author can delete this post")
    scope = await db.scalar(select(SocialShareScope).where(SocialShareScope.build_id == build.id))
    photos = list(await db.scalars(select(SocialPhoto).where(SocialPhoto.build_id == build.id)))
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    if scope:
        await db.delete(scope)
    for photo in photos:
        await db.delete(photo)
    await db.delete(build)
    await db.commit()
