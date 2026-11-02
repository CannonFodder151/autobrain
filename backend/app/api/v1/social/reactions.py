from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.social.common import *

router = APIRouter(tags=["social-reactions"])

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


