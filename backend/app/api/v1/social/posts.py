"""Post CRUD endpoints: create, get, update, delete"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.social.federation import FederationUnavailable
from app.social.media import MAX_UPLOAD_BYTES, MediaError, read_upload, signed_url, upload_photo
from app.social.models import (
    SocialBuild,
    SocialBuildFlag,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialRemoteTombstone,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot, dumps, loads
from app.api.v1.social.helpers import _serialize, _purge_build

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_premium)])


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
    """Full build edit: title, caption, photo order/swap and scope."""
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=1000)
    photo_ids: list[str] | None = Field(default=None, max_length=12)
    share_scope: ShareScopeIn | None = None


@router.post("/posts", status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Create a new build post."""
    vehicle = await get_accessible_vehicle(db, payload.vehicle_id, user)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    build = SocialBuild(
        author_user_id=user.id,
        vehicle_id=vehicle.id,
        title=payload.title,
        caption=payload.caption,
        published=False,
    )
    db.add(build)
    await db.flush()

    for i, pid in enumerate(payload.photo_ids):
        photo = await db.get(SocialPhoto, pid)
        if photo and photo.build_id is None:
            photo.build_id = build.id
            photo.position = i

    if payload.share_scope:
        scope = SocialShareScope(
            build_id=build.id,
            viewer_user_id=user.id,
            allow_photos=payload.share_scope.allow_photos,
            allow_specs=payload.share_scope.allow_specs,
            allow_mods=payload.share_scope.allow_mods,
            allow_odometer=payload.share_scope.allow_odometer,
            allow_notes=payload.share_scope.allow_notes,
        )
        db.add(scope)

    await db.commit()
    await db.refresh(build)
    return await _serialize(db, build, user)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
):
    """Get a single post by ID."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if not build.published and build.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not published")

    return await _serialize(db, build, user)


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: str,
    payload: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Edit a post (title, caption, photos, share scope)."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if build.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")

    # Use model_fields_set to distinguish between "not provided" and "explicitly set to null"
    if "title" in payload.model_fields_set:
        build.title = payload.title
    if "caption" in payload.model_fields_set:
        build.caption = payload.caption
    build.updated_at = datetime.now(timezone.utc)

    if "photo_ids" in payload.model_fields_set:
        current = list(
            (await db.execute(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id)
            )).scalars().all()
        )
        for p in current:
            p.build_id = None
        for i, pid in enumerate(payload.photo_ids or []):
            photo = await db.get(SocialPhoto, pid)
            if photo:
                photo.build_id = build.id
                photo.position = i

    if "share_scope" in payload.model_fields_set and payload.share_scope is not None:
        await db.execute(
            delete(SocialShareScope).where(SocialShareScope.build_id == build.id)
        )
        scope = SocialShareScope(
            build_id=build.id,
            viewer_user_id=user.id,
            allow_photos=payload.share_scope.allow_photos,
            allow_specs=payload.share_scope.allow_specs,
            allow_mods=payload.share_scope.allow_mods,
            allow_odometer=payload.share_scope.allow_odometer,
            allow_notes=payload.share_scope.allow_notes,
        )
        db.add(scope)

    await db.commit()
    await db.refresh(build)
    return await _serialize(db, build, user)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Delete a post (author or admin)."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if build.author_user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=404, detail="Post not found")

    await _purge_build(db, build)
    return None
