"""Comment endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.db.session import get_db
from app.models.user import User
from app.social.models import (
    SocialBuild,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.rate_limit import social_rate_limit
from app.api.v1.social.helpers import _serialize, _push_event_safe

router = APIRouter(dependencies=[Depends(require_premium)])


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


@router.post("/posts/{post_id}/comments", status_code=201)
async def add_comment(
    post_id: str,
    payload: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(15)),
):
    """Add a comment to a post."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    if build.status != "published":
        raise HTTPException(status_code=403, detail="Post not published")

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
    await _push_event_safe(db, build, "comment", {
        "body": payload.body,
        "author_display_name": user.display_name,
        "server_name": cfg.server_name,
    })
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
    user: User = Depends(require_premium),
):
    """List comments on a post."""
    build = await db.get(SocialBuild, post_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")

    comments = list(
        (await db.execute(
            select(SocialComment)
            .where(SocialComment.build_id == build.id)
            .order_by(SocialComment.created_at)
        )).scalars().all()
    )

    return [
        {
            "id": c.id,
            "author_user_id": c.author_user_id,
            "body": c.body,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in comments
    ]
