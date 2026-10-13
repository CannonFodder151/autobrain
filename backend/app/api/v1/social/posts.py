"""Social posts CRUD endpoints."""

import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.social.federation import FederationUnavailable
from app.social.media import MAX_UPLOAD_BYTES
from app.social.models import (
    SocialBuild,
    SocialBuildFlag,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.rate_limit import social_rate_limit
from app.social.snapshot import build_snapshot, dumps, loads

logger = get_logger(__name__)


class ShareScopeIn(BaseModel):
    allow_photos: bool = True
    allow_specs: bool = True
    allow_mods: bool = True
    allow_odometer: bool = False
    allow_notes: bool = False


class PostCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=36)
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=1000)
    share_scope: ShareScopeIn = ShareScopeIn()
    photo_ids: list[str] = Field(default_factory=list, max_length=15)


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=1000)
    photo_ids: list[str] | None = Field(default=None, max_length=12)
    share_scope: ShareScopeIn | None = None


router = APIRouter(
    prefix="/social",
    tags=["social"],
    dependencies=[Depends(lambda db=Depends(get_db): None)],  # feature gate applied in __init__
)


async def require_social_feature(db: AsyncSession = Depends(get_db)) -> None:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        raise HTTPException(status_code=403, detail="Disabled by your admin")


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
    photo_ids: list[str] = []
    scope = await db.scalar(
        select(SocialShareScope).where(SocialShareScope.build_id == build.id)
    )
    share_scope = {
        "allow_photos": scope.allow_photos if scope else True,
        "allow_specs": scope.allow_specs if scope else True,
        "allow_mods": scope.allow_mods if scope else True,
        "allow_odometer": scope.allow_odometer if scope else False,
        "allow_notes": scope.allow_notes if scope else False,
    }
    if build.origin in ("local", "demo") and build.vehicle_id:
        vehicle = await db.get(Vehicle, build.vehicle_id)
        if vehicle:
            photos = list(await db.scalars(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.position, SocialPhoto.created_at)
            ))
            snapshot = await build_snapshot(db, vehicle, scope, [p.file_key for p in photos])
            photo_keys = list(snapshot.get("photo_keys", []))
            photo_ids = [p.id for p in photos]
    photos: list[str] = []
    for key in photo_keys:
        try:
            from app.social.media import signed_url
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
    is_author = viewer is not None and build.author_user_id is not None and viewer.id == build.author_user_id
    return {
        "id": build.id,
        "title": build.title,
        "caption": build.caption,
        "author_display_name": build.remote_author_display_name or build.author_display_name,
        "server_name": build.server_name,
        "origin": build.origin,
        "snapshot": snapshot,
        "photos": photos,
        "photo_ids": photo_ids if is_author else [],
        "share_scope": share_scope,
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


async def _purge_build(db: AsyncSession, build: SocialBuild) -> None:
    await db.execute(
        update(SocialPhoto)
        .where(SocialPhoto.build_id == build.id)
        .values(build_id=None)
    )
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.delete(build)


async def _tombstone_removed_build(db: AsyncSession, build: SocialBuild) -> None:
    if build.origin == "remote" and build.remote_build_id:
        await db.merge(SocialBuildFlag(remote_build_id=build.remote_build_id))
        return
    if build.origin != "local":
        return
    cfg = await get_server_config(db)
    if cfg.federation_enabled and cfg.hub_status in ("registered", "pending") and cfg.hub_server_id:
        await db.merge(SocialBuildFlag(remote_build_id=build.id))


async def _push_outbox_safe(db: AsyncSession, cfg, build: SocialBuild, snapshot: dict, photo_keys: list[str]) -> None:
    try:
        from app.social.federation import push_outbox
        await push_outbox(cfg, build.id, {
            "build_id": build.id,
            "title": snapshot.get("title"),
            "caption": build.caption,
            "author_display_name": build.author_display_name,
            "server_name": build.server_name or cfg.server_name,
            "snapshot": snapshot,
            "photo_urls": [await signed_url(k) for k in photo_keys],
        })
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_outbox_push_failed", build_id=build.id, error=str(exc))


@router.get("/feed")
async def feed(
    limit: int = Depends(20),
    q: str | None = Depends(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(24)),
) -> dict:
    await _sync_federation(db)
    await db.commit()
    stmt = select(SocialBuild).where(SocialBuild.status == "published")
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            SocialBuild.title.ilike(needle)
            | SocialBuild.caption.ilike(needle)
            | SocialBuild.author_display_name.ilike(needle)
            | SocialBuild.server_name.ilike(needle)
        )
    rows = await db.scalars(
        stmt.order_by(SocialBuild.created_at.desc()).limit(limit)
    )
    return {"items": [await _serialize(db, b, user) for b in rows]}


@router.get("/my-posts")
async def my_posts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(24)),
) -> dict:
    rows = await db.scalars(
        select(SocialBuild)
        .where(
            SocialBuild.status == "published",
            SocialBuild.author_user_id == user.id,
        )
        .order_by(SocialBuild.created_at.desc())
        .limit(200)
    )
    return {"items": [await _serialize(db, b, user) for b in rows]}


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
        await _push_outbox_safe(db, cfg, build, snapshot, photo_keys)
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
                photo.build_id = None
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
        await _push_outbox_safe(db, cfg, build, snapshot, photo_keys)
    return await _serialize(db, build, user)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> None:
    build = await _get_published(db, post_id)
    is_author = build.author_user_id == user.id
    if not is_author and user.role != "admin":
        raise HTTPException(status_code=404, detail="Post not found")
    origin = build.origin
    await _tombstone_removed_build(db, build)
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
    if origin == "local":
        cfg = await get_server_config(db)
        if cfg.federation_enabled and cfg.hub_status == "registered" and cfg.hub_server_id:
            try:
                from app.social.federation import push_removed
                await push_removed(cfg, str(build.id), "build")
            except (FederationUnavailable, Exception) as exc:
                logger.warning("social_remove_push_failed", build_id=build.id, error=str(exc))