"""Feed and my-posts routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium
from app.db.session import get_db
from app.models.user import User
from app.social.rate_limit import social_rate_limit
from app.social.models import SocialBuild

from app.api.v1.social._common import (
    _serialize,
    _sync_federation,
)

router = APIRouter()


@router.get("/feed")
async def feed(
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=120),
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
    """The caller's own builds (My Builds tab, AUT-501). Local-only; remote
    copies have no local author."""
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