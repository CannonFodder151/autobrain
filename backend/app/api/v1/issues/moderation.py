"""Social Issues Blog — moderation (flag) endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.social.models import SocialIssueComment, SocialIssueFlag, get_server_config
from app.social.rate_limit import social_rate_limit, social_user_rate_limit

from app.api.v1.issues.schemas import FlagIn, _plaintext
from app.api.v1.issues.posts import _get_visible

logger = get_logger(__name__)


router = APIRouter(prefix="/social/issues", tags=["social-issues"])


@router.post("/{post_id}/flag", status_code=201)
async def flag_issue(
    post_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("issues-flag", 5)),
) -> dict:
    post = await _get_visible(db, post_id)
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialIssueFlag).where(
            SocialIssueFlag.post_id == post.id,
            SocialIssueFlag.flagged_by_user_id == user.id,
            SocialIssueFlag.comment_id.is_(None),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this post")
    db.add(SocialIssueFlag(
        post_id=post.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}


@router.post("/{post_id}/comments/{comment_id}/flag", status_code=201)
async def flag_issue_comment(
    post_id: str,
    comment_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("issues-flag-comment", 5)),
) -> dict:
    """Report a comment on an issue post (AUT-832 moderation queue)."""
    post = await _get_visible(db, post_id)
    comment = await db.get(SocialIssueComment, comment_id)
    if not comment or comment.post_id != post.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    reason = _plaintext(payload.reason).strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Reason cannot be empty")
    existing = await db.scalar(
        select(SocialIssueFlag).where(
            SocialIssueFlag.comment_id == comment.id,
            SocialIssueFlag.flagged_by_user_id == user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already flagged this comment")
    db.add(SocialIssueFlag(
        post_id=post.id,
        comment_id=comment.id,
        flagged_by_user_id=user.id,
        reason=reason,
    ))
    await db.commit()
    return {"message": "Flag submitted for review"}