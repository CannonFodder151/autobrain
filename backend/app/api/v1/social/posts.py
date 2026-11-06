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
from app.social import federation
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
                select(SocialPhoto).where(SocialPhoto.vehicle_id == build.vehicle_id)
            ))
            for photo in photos:
                if photo.key in photo_keys:
                    photo_ids.append(photo.id)
    liked = viewer is not None and await db.scalar(
        select(SocialLike).where(
            SocialLike.build_id == build.id,
            SocialLike.user_id == viewer.id,
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


async def _push_event_safe(db: AsyncSession, build: SocialBuild, kind: str, payload: dict) -> None:
    """Fan a comment/like out to the hub so remote copies stay in sync (FD-1).

    Events reference the build id on its origin server: the local id for local
    builds, the origin id for remote copies (so the origin can match them).
    """
    cfg = await get_server_config(db)
    origin_build_id = build.remote_build_id if build.origin == "remote" else build.id
    try:
        await federation.push_event(cfg, origin_build_id, kind, payload)
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_event_push_failed", kind=kind, build_id=build.id, error=str(exc))


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
    await db.delete(build)


@router.post("", response_model=dict, status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(24)),
) -> dict:
    cfg = await get_server_config(db)
    vehicle = await get_accessible_vehicle(db, user.id, payload.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    build = SocialBuild(
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        vehicle_id=payload.vehicle_id,
        title=payload.title,
        caption=payload.caption,
        snapshot_json=dumps(build_snapshot(db, vehicle, payload.photo_ids)),
        origin="local",
        status="published",
    )
    db.add(build)
    await db.commit()
    await db.refresh(build)
    scope = SocialShareScope(
        build_id=build.id,
        allow_photos=payload.share_scope.allow_photos,
        allow_specs=payload.share_scope.allow_specs,
        allow_mods=payload.share_scope.allow_mods,
        allow_odometer=payload.share_scope.allow_odometer,
        allow_notes=payload.share_scope.allow_notes,
    )
    db.add(scope)
    await db.commit()
    return await _serialize(db, build, user)


@router.get("", response_model=list[dict])
async def list_posts(
    limit: int = 20,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(24)),
) -> list[dict]:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        return []
    stmt = (
        select(SocialBuild)
        .where(SocialBuild.status == "published")
        .order_by(SocialBuild.created_at.desc())
        .limit(limit)
    )
    builds = list(await db.scalars(stmt))
    return [await _serialize(db, b, user) for b in builds]


@router.get("/{build_id}", response_model=dict)
async def get_post(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, build_id)
    return await _serialize(db, build, user)


@router.patch("/{build_id}", response_model=dict)
async def update_post(
    build_id: str,
    payload: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, build_id)
    if build.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not author")
    if payload.title is not None:
        build.title = payload.title
    if payload.caption is not None:
        build.caption = payload.caption
    if payload.photo_ids is not None:
        build.snapshot_json = dumps(build_snapshot(db, build.vehicle, payload.photo_ids))
    if payload.share_scope is not None:
        scope = await db.scalar(
            select(SocialShareScope).where(SocialShareScope.build_id == build.id)
        )
        if scope:
            scope.allow_photos = payload.share_scope.allow_photos
            scope.allow_specs = payload.share_scope.allow_specs
            scope.allow_mods = payload.share_scope.allow_mods
            scope.allow_odometer = payload.share_scope.allow_odometer
            scope.allow_notes = payload.share_scope.allow_notes
    await db.commit()
    await _push_event_safe(db, build, "post.updated", {"build_id": build.id})
    return await _serialize(db, build, user)


@router.delete("/{build_id}", status_code=204)
async def delete_post(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> None:
    build = await _get_published(db, build_id)
    if build.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not author")
    await _purge_build(db, build)
    await db.commit()


@router.post("/{build_id}/like", response_model=dict)
async def like_post(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, build_id)
    existing = await db.scalar(
        select(SocialLike).where(
            SocialLike.build_id == build.id,
            SocialLike.user_id == user.id,
        )
    )
    if existing:
        await db.delete(existing)
        await db.commit()
        await _push_event_safe(db, build, "like.removed", {"build_id": build.id, "user_id": user.id})
        return {"liked": False}
    like = SocialLike(build_id=build.id, user_id=user.id)
    db.add(like)
    await db.commit()
    await _push_event_safe(db, build, "like.added", {"build_id": build.id, "user_id": user.id})
    return {"liked": True}


@router.post("/{build_id}/comments", response_model=dict, status_code=201)
async def add_comment(
    build_id: str,
    text: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, build_id)
    comment = SocialComment(build_id=build.id, user_id=user.id, text=text)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    await _push_event_safe(db, build, "comment.added", {"build_id": build.id, "comment_id": comment.id})
    return {"id": comment.id, "text": comment.text, "created_at": comment.created_at.isoformat()}


@router.get("/{build_id}/comments", response_model=list[dict])
async def list_comments(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> list[dict]:
    build = await _get_published(db, build_id)
    comments = list(await db.scalars(
        select(SocialComment)
        .where(SocialComment.build_id == build.id)
        .order_by(SocialComment.created_at.desc())
    ))
    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "text": c.text,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]


@router.post("/{build_id}/share", response_model=dict)
async def share_post(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, build_id)
    await _push_event_safe(db, build, "share", {"build_id": build.id, "user_id": user.id})
    return {"shared": True}


@router.post("/{build_id}/report", response_model=dict)
async def report_post(
    build_id: str,
    reason: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> dict:
    build = await _get_published(db, build_id)
    flag = SocialBuildFlag(build_id=build.id, reason=reason, reporter_id=user.id)
    db.add(flag)
    await db.commit()
    return {"reported": True}
