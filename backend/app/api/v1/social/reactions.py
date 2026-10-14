"""Like routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.db.session import get_db
from app.models.user import User
from app.social.rate_limit import social_rate_limit
from app.social.models import SocialLike, get_server_config

from app.api.v1.social._common import (
    _get_published,
    _like_count,
    _push_event_safe,
)

router = APIRouter()


@router.post("/posts/{post_id}/likes")
async def toggle_like(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(20)),
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
    await _push_event_safe(db, build, "like", {
        "liked": liked,
        "author_display_name": user.display_name,
        "server_name": cfg.server_name,
    })
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