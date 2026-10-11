"""Social Issues Blog — comment endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.social.models import SocialIssueComment, SocialPhoto, get_server_config
from app.social.rate_limit import social_rate_limit, social_user_rate_limit

from app.api.v1.issues.schemas import CommentIn, _plaintext
from app.api.v1.issues.posts import _get_visible, _comment_photo_url
from app.api.v1.issues.federation import _push_issue_event_safe

logger = get_logger(__name__)


router = APIRouter(prefix="/social/issues", tags=["social-issues"])


@router.post("/{post_id}/comments", status_code=201)
async def add_comment(
    post_id: str,
    payload: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
    _user_rl: None = Depends(social_user_rate_limit("issues-comment", 10)),
) -> dict:
    post = await _get_visible(db, post_id)
    body = _plaintext(payload.body).strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")
    cfg = await get_server_config(db)
    comment = SocialIssueComment(
        post_id=post.id,
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        body=body,
    )
    db.add(comment)
    await db.flush()
    if payload.photo_id:
        photo = await db.scalar(
            select(SocialPhoto).where(
                SocialPhoto.id == payload.photo_id,
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.build_id.is_(None),
                SocialPhoto.issue_id.is_(None),
                SocialPhoto.comment_id.is_(None),
            )
        )
        if photo is None:
            raise HTTPException(
                status_code=422,
                detail="Photo is invalid (wrong owner or already attached)",
            )
        photo.comment_id = comment.id
    await db.commit()
    await _push_issue_event_safe(db, post, {
        "comment_id": str(comment.id),
        "post_type": "issue",
        "author_display_name": comment.author_display_name,
        "server_name": comment.server_name,
        "body": comment.body,
        "is_answer": False,
    })
    return {
        "id": comment.id,
        "post_id": post.id,
        "author_display_name": comment.author_display_name,
        "server_name": comment.server_name,
        "body": comment.body,
        "photo": await _comment_photo_url(db, comment.id),
        "is_answer": False,
        "created_at": comment.created_at.isoformat(),
    }


@router.post("/{post_id}/comments/{comment_id}/answer", status_code=200)
async def mark_answer(
    post_id: str,
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
    _user_rl: None = Depends(social_user_rate_limit("issues-answer", 10)),
) -> dict:
    """Pin a comment as the answer and resolve the post (post author only;
    everyone else gets 404 so posts cannot be probed)."""
    post = await _get_visible(db, post_id)
    comment = await db.get(SocialIssueComment, comment_id)
    if not comment or comment.post_id != post.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if user.id != post.author_user_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    previous = await db.scalar(
        select(SocialIssueComment).where(
            SocialIssueComment.post_id == post.id,
            SocialIssueComment.is_answer.is_(True),
        )
    )
    if previous is not None:
        previous.is_answer = False
    comment.is_answer = True
    post.resolved_comment_id = comment.id
    post.status = "resolved"
    await db.commit()
    # The hub only relays `comment`/`like` event types, so an answer travels as
    # a comment event with is_answer=true; receivers match the origin comment id.
    await _push_issue_event_safe(db, post, {
        "comment_id": str(comment.id),
        "post_type": "issue",
        "author_display_name": comment.author_display_name,
        "server_name": comment.server_name,
        "body": comment.body,
        "is_answer": True,
    })
    return {"id": comment.id, "is_answer": True, "status": post.status}