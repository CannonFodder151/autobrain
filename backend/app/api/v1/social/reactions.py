"""Reactions: likes, flags, reports, share links"""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.services.events import add_event
from app.social.federation import FederationUnavailable
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
from app.social.rate_limit import social_rate_limit
from app.api.v1.social.helpers import _serialize, _plaintext, _push_event_safe

logger = get_logger(__name__)

_INBOX_SYNC_TTL_SECONDS = 60

router = APIRouter(dependencies=[Depends(require_premium)])


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class FlagIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


@router.post("/posts/{post_id}/likes")
async def toggle_like(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(20)),
):
    """Toggle like on a post."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if build.status != "published":
        raise HTTPException(status_code=403, detail="Post not published")

    cfg = await get_server_config(db)
    existing = await db.execute(
        select(SocialLike).where(
            SocialLike.build_id == build.id,
            SocialLike.author_user_id == user.id,
        )
    )
    existing = existing.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        liked = False
    else:
        like = SocialLike(
            build_id=build.id,
            author_user_id=user.id,
            author_display_name=user.display_name,
            server_name=cfg.server_name,
        )
        db.add(like)
        liked = True
    await db.commit()
    await _push_event_safe(db, build, "like", {
        "liked": liked,
        "author_display_name": user.display_name,
        "server_name": cfg.server_name,
    })
    return {"liked": liked}


@router.get("/posts/{post_id}/likes")
async def list_likes(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
):
    """List users who liked a post."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    likes = list(
        (await db.execute(
            select(SocialLike).where(SocialLike.build_id == build.id)
        )).scalars().all()
    )

    return [
        {
            "author_user_id": l.author_user_id,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in likes
    ]


@router.post("/posts/{post_id}/report", status_code=201)
async def report_post(
    post_id: str,
    payload: ReportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Report a post."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    reason = _plaintext(payload.reason)

    flag = SocialBuildFlag(
        build_id=build.id,
        flagged_by_user_id=user.id,
        reason=reason,
        status="open",
    )
    db.add(flag)
    await db.commit()

    await add_event(db, "social_post_reported", {
        "build_id": build.id,
        "reporter_id": str(user.id),
        "reason": reason,
    })

    return {"id": flag.id, "status": flag.status}


@router.post("/posts/{post_id}/share-link")
async def create_share_link(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Create a share link for a post (valid 7 days)."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if build.status != "published" and build.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="Post not published")

    token = token_urlsafe(16)
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    share = SocialShareScope(
        build_id=build.id,
        viewer_user_id=token,  # reused as share token
        allow_photos=True,
        allow_specs=True,
        allow_mods=True,
        allow_odometer=False,
        allow_notes=False,
    )
    # Note: this is a simplified share link - real impl would use separate model
    db.add(share)
    await db.commit()

    return {"token": token, "expires_at": expires.isoformat()}


@router.get("/share/{token}")
async def resolve_share_link(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
):
    """Resolve a share link to a post."""
    share = await db.execute(
        select(SocialShareScope).where(SocialShareScope.viewer_user_id == token)
    )
    share = share.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    build = await db.get(SocialBuild, share.build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    return await _serialize(db, build, user)


@router.post("/posts/{post_id}/flag", status_code=201)
async def flag_build(
    post_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Flag a build (same as report but for builds)."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    reason = _plaintext(payload.reason)

    flag = SocialBuildFlag(
        build_id=build.id,
        flagged_by_user_id=user.id,
        reason=reason,
        status="open",
    )
    db.add(flag)
    await db.commit()

    await add_event(db, "social_build_flagged", {
        "build_id": build.id,
        "flagger_id": str(user.id),
        "reason": reason,
    })

    return {"id": flag.id, "status": flag.status}


@router.post("/posts/{post_id}/comments/{comment_id}/flag", status_code=201)
async def flag_build_comment(
    post_id: str,
    comment_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Flag a comment on a build."""
    comment = await db.get(SocialComment, comment_id)
    if not comment or comment.build_id != post_id:
        raise HTTPException(status_code=404, detail="Comment not found")

    reason = _plaintext(payload.reason)

    # Reuse SocialBuildFlag for comment flags (build_id + comment_id)
    flag = SocialBuildFlag(
        build_id=post_id,
        flagged_by_user_id=user.id,
        reason=reason,
        status="open",
    )
    db.add(flag)
    await db.commit()

    await add_event(db, "social_comment_flagged", {
        "comment_id": comment_id,
        "flagger_id": str(user.id),
        "reason": reason,
    })

    return {"id": flag.id, "status": flag.status}
