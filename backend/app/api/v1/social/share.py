"""Social share link endpoints."""

import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.db.session import get_db
from app.models.user import User
from app.social.models import SocialBuild
from app.social.rate_limit import social_rate_limit

from app.api.v1.social.posts import _get_published, _serialize

router = APIRouter(prefix="/social", tags=["social"])


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