"""Social moderation endpoints (reports and flags)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.social.federation import FederationUnavailable
from app.social.models import SocialBuildFlag, get_server_config
from app.social.rate_limit import social_rate_limit, social_user_rate_limit

from app.api.v1.social.posts import _get_published

logger = get_logger(__name__)


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class FlagIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


def _plaintext(value: str) -> str:
    return "".join(c for c in value if c >= " " or c in "\n\t")


router = APIRouter(prefix="/social", tags=["social"])


@router.post("/posts/{post_id}/report", status_code=201)
async def report_post(
    post_id: str,
    payload: ReportIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    build = await _get_published(db, post_id)
    existing = await db.scalar(select(SocialBuildFlag).where(
        SocialBuildFlag.build_id == build.id,
        SocialBuildFlag.flagged_by_user_id == user.id,
    ))
    if existing:
        existing.reason = payload.reason
    else:
        db.add(SocialBuildFlag(
            build_id=build.id,
            flagged_by_user_id=user.id,
            reason=payload.reason,
        ))
    await db.commit()
    cfg = await get_server_config(db)
    if cfg.federation_enabled and cfg.hub_status == "registered":
        origin_build_id = build.remote_build_id if build.origin == "remote" else build.id
        try:
            from app.social.federation import push_report
            await push_report(
                cfg, origin_build_id, payload.reason, user.display_name, cfg.server_name
            )
        except (FederationUnavailable, Exception) as exc:
            logger.warning("social_report_push_failed", build_id=build.id, error=str(exc))
    return {"reported": True}


@router.post("/posts/{post_id}/flag", status_code=201)
async def flag_build(
    post_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("builds-flag", 5)),
) -> dict:
    build = await _get_published(db, post_id)
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialBuildFlag).where(
            SocialBuildFlag.build_id == build.id,
            SocialBuildFlag.flagged_by_user_id == user.id,
            SocialBuildFlag.comment_id.is_(None),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this post")
    db.add(SocialBuildFlag(
        build_id=build.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}


@router.post("/posts/{post_id}/comments/{comment_id}/flag", status_code=201)
async def flag_build_comment(
    post_id: str,
    comment_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("builds-flag-comment", 5)),
) -> dict:
    build = await _get_published(db, post_id)
    comment = await db.get(SocialComment, comment_id)
    if not comment or comment.build_id != build.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialBuildFlag).where(
            SocialBuildFlag.comment_id == comment.id,
            SocialBuildFlag.flagged_by_user_id == user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this comment")
    db.add(SocialBuildFlag(
        build_id=build.id,
        comment_id=comment.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}