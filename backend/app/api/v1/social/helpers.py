"""Shared helpers for social routes."""

from fastapi import Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.social import federation
from app.social.federation import FederationUnavailable
from app.social.models import (
    SocialBuild,
    SocialBuildFlag,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot
import logging

logger = logging.getLogger(__name__)


async def _serialize(db: AsyncSession, build: SocialBuild, viewer) -> dict:
    """Serialise a build for feed/list responses."""
    flags = list(
        (await db.execute(
            select(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id)
        )).scalars().all()
    )
    photos = list(
        (await db.execute(
            select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.position)
        )).scalars().all()
    )
    likes = list(
        (await db.execute(
            select(SocialLike).where(SocialLike.build_id == build.id)
        )).scalars().all()
    )
    comments = list(
        (await db.execute(
            select(SocialComment).where(SocialComment.build_id == build.id).order_by(SocialComment.created_at)
        )).scalars().all()
    )
    scopes = list(
        (await db.execute(
            select(SocialShareScope).where(SocialShareScope.build_id == build.id)
        )).scalars().all()
    )

    viewer_id = str(viewer.id) if viewer else None
    liked = any(l.author_user_id == viewer_id for l in likes) if viewer_id else False

    photo_data = []
    for p in photos:
        photo_data.append({
            "id": p.id,
            "key": p.key,
            "url": p.url,
            "thumb_url": p.thumb_url,
            "position": p.position,
        })

    scope_data = {}
    for s in scopes:
        scope_data[str(s.viewer_user_id)] = {
            "allow_photos": s.allow_photos,
            "allow_specs": s.allow_specs,
            "allow_mods": s.allow_mods,
            "allow_odometer": s.allow_odometer,
            "allow_notes": s.allow_notes,
        }

    return {
        "id": build.id,
        "author_user_id": build.author_user_id,
        "vehicle_id": build.vehicle_id,
        "title": build.title,
        "caption": build.caption,
        "created_at": build.created_at.isoformat() if build.created_at else None,
        "updated_at": build.updated_at.isoformat() if build.updated_at else None,
        "photos": photo_data,
        "like_count": len(likes),
        "comment_count": len(comments),
        "liked": liked,
        "scopes": scope_data,
        "flags": [
            {"id": f.id, "reason": f.reason, "status": f.status}
            for f in flags
        ],
    }


async def _purge_build(db: AsyncSession, build: SocialBuild) -> None:
    """Hard-delete a build and all children (cascade)."""
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.delete(build)
    await db.commit()


async def _tombstone_removed_build(db: AsyncSession, build: SocialBuild) -> None:
    """Mark a remote build as removed (tombstone)."""
    from app.social.models import SocialRemoteTombstone
    tombstone = SocialRemoteTombstone(
        build_id=build.id,
        removed_at=build.updated_at,
    )
    db.add(tombstone)
    await db.commit()


async def _sync_federation(db: AsyncSession) -> None:
    """Pull remote builds + push local outbox."""
    from app.social.federation import get_federated_feed, push_outbox
    from app.social.models import SocialBuild, get_server_config

    try:
        remote = await get_federated_feed(db, limit=100, offset=0)
        for r in remote:
            existing = await db.get(SocialBuild, r.id)
            if not existing:
                local = SocialBuild(
                    id=r.id,
                    author_user_id=r.author_user_id,
                    vehicle_id=r.vehicle_id,
                    title=r.title,
                    caption=r.caption,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    published=r.published,
                )
                db.add(local)
        await db.commit()
    except FederationUnavailable:
        pass

    try:
        await push_outbox(db)
    except FederationUnavailable:
        pass


def _plaintext(value: str) -> str:
    """Strip control characters."""
    return "".join(c for c in value if c >= " " or c in "\n\t")


async def require_social_feature(db: AsyncSession = Depends(get_db)) -> None:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        raise HTTPException(status_code=403, detail="Disabled by your admin")


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
        logger.warning("social_event_push_failed kind=%s build_id=%s error=%s", kind, build.id, exc)
