from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.social.common import *

router = APIRouter(tags=["social-comments"])

@router.post("/posts/{post_id}/comments", status_code=201)
async def add_comment(
    post_id: str,
    payload: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(15)),
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


