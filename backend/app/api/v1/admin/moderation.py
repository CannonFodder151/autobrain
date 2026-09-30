"""Admin moderation hub for Issues Blog + Community Garage builds (AUT-832,
AUT-883). Covers flag queue, review hub, item deletes, and social bans."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

logger = get_logger(__name__)


# --- Shared models ---


class _IssueModerationUpdate(BaseModel):
    status_hidden: bool | None = None
    status: str | None = None


async def _best_effort_delete_media(file_keys: list[str]) -> None:
    """Best-effort MinIO cleanup on admin takedowns (AUT-832 F4). Object removal
    must never fail a moderation delete, so any storage error is swallowed."""
    if not file_keys:
        return
    try:
        from app.core.storage import delete_object

        for key in file_keys:
            await delete_object(key)
    except Exception:
        return


# --- Issues Blog moderation ---


@router.get("/issues/flagged")
async def flagged_issues(db: AsyncSession = Depends(get_db)) -> dict:
    """Moderation queue: every flagged issue post with its flag count."""
    from app.social.models import SocialIssueFlag, SocialIssuePost

    rows = await db.execute(
        select(
            SocialIssuePost.id,
            SocialIssuePost.title,
            SocialIssuePost.status,
            SocialIssuePost.status_hidden,
            SocialIssuePost.author_user_id,
            SocialIssuePost.author_display_name,
            SocialIssuePost.created_at,
            func.count(SocialIssueFlag.id).label("flag_count"),
        )
        .join(SocialIssueFlag, SocialIssueFlag.post_id == SocialIssuePost.id)
        .where(SocialIssueFlag.comment_id.is_(None))
        .group_by(SocialIssuePost.id)
        .order_by(func.count(SocialIssueFlag.id).desc())
    )
    return {
        "items": [
            {
                "kind": "post",
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "status_hidden": r.status_hidden,
                "author_user_id": r.author_user_id,
                "author_display_name": r.author_display_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "flag_count": r.flag_count,
            }
            for r in rows
        ]
    }


@router.get("/issues/review")
async def review_queue(db: AsyncSession = Depends(get_db)) -> dict:
    """Unified moderation hub (AUT-832 + AUT-883): every flagged issue OR build
    post/comment with the reporting reasons and author info, newest report
    first. `target` distinguishes issue entries from build entries so the hub
    can route deletes to the right admin endpoint."""
    from app.social.models import (
        SocialBuild,
        SocialBuildFlag,
        SocialComment,
        SocialIssueComment,
        SocialIssueFlag,
        SocialIssuePost,
    )

    items: list[dict] = []

    stmt = (
        select(
            SocialIssueFlag.id.label("flag_id"),
            SocialIssueFlag.reason,
            SocialIssueFlag.created_at.label("flagged_at"),
            SocialIssuePost.id.label("post_id"),
            SocialIssuePost.title.label("post_title"),
            SocialIssuePost.body.label("post_body"),
            SocialIssuePost.created_at.label("post_created_at"),
            SocialIssuePost.status_hidden,
            SocialIssuePost.author_user_id.label("post_author_id"),
            SocialIssuePost.author_display_name.label("post_author_name"),
            SocialIssueComment.id.label("comment_id"),
            SocialIssueComment.author_user_id.label("comment_author_id"),
            SocialIssueComment.author_display_name.label("comment_author_name"),
            SocialIssueComment.body.label("comment_body"),
            SocialIssueComment.created_at.label("comment_created_at"),
        )
        .join(SocialIssuePost, SocialIssuePost.id == SocialIssueFlag.post_id)
        .outerjoin(SocialIssueComment, SocialIssueComment.id == SocialIssueFlag.comment_id)
        .order_by(SocialIssueFlag.created_at.desc())
        .limit(200)
    )
    for r in (await db.execute(stmt)).all():
        items.append({
            "flag_id": r.flag_id,
            "reason": r.reason,
            "flagged_at": r.flagged_at.isoformat() if r.flagged_at else None,
            "target": "issue",
            "kind": "comment" if r.comment_id else "post",
            "post_id": r.post_id,
            "post_title": r.post_title,
            "post_body": r.post_body,
            "post_created_at": r.post_created_at.isoformat() if r.post_created_at else None,
            "post_hidden": r.status_hidden,
            "post_author_user_id": r.post_author_id,
            "post_author_display_name": r.post_author_name,
            "comment_id": r.comment_id,
            "comment_body": r.comment_body,
            "comment_created_at": r.comment_created_at.isoformat() if r.comment_created_at else None,
            "comment_author_user_id": r.comment_author_id,
            "comment_author_display_name": r.comment_author_name,
        })

    build_stmt = (
        select(
            SocialBuildFlag.id.label("flag_id"),
            SocialBuildFlag.reason,
            SocialBuildFlag.created_at.label("flagged_at"),
            SocialBuild.id.label("post_id"),
            SocialBuild.title.label("post_title"),
            SocialBuild.caption.label("post_caption"),
            SocialBuild.status.label("build_status"),
            SocialBuild.created_at.label("post_created_at"),
            SocialBuild.author_user_id.label("post_author_id"),
            SocialBuild.author_display_name.label("post_author_name"),
            SocialComment.id.label("comment_id"),
            SocialComment.author_user_id.label("comment_author_id"),
            SocialComment.author_display_name.label("comment_author_name"),
            SocialComment.body.label("comment_body"),
            SocialComment.created_at.label("comment_created_at"),
        )
        .join(SocialBuild, SocialBuild.id == SocialBuildFlag.build_id)
        .outerjoin(SocialComment, SocialComment.id == SocialBuildFlag.comment_id)
        .order_by(SocialBuildFlag.created_at.desc())
        .limit(200)
    )
    for r in (await db.execute(build_stmt)).all():
        items.append({
            "flag_id": r.flag_id,
            "reason": r.reason,
            "flagged_at": r.flagged_at.isoformat() if r.flagged_at else None,
            "target": "build",
            "kind": "comment" if r.comment_id else "post",
            "post_id": r.post_id,
            "post_title": r.post_title,
            "post_caption": r.post_caption,
            "post_created_at": r.post_created_at.isoformat() if r.post_created_at else None,
            "post_hidden": r.build_status != "published",
            "post_author_user_id": r.post_author_id,
            "post_author_display_name": r.post_author_name,
            "comment_id": r.comment_id,
            "comment_body": r.comment_body,
            "comment_created_at": r.comment_created_at.isoformat() if r.comment_created_at else None,
            "comment_author_user_id": r.comment_author_id,
            "comment_author_display_name": r.comment_author_name,
        })

    items.sort(key=lambda i: i["flagged_at"] or "", reverse=True)
    return {"items": items[:200]}


@router.delete("/issues/comments/{comment_id}", status_code=204)
async def delete_comment_admin(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a single issue comment (moderation hub, AUT-832)."""
    from app.social.models import SocialIssueComment, SocialIssueFlag, SocialIssuePost, SocialPhoto

    comment = await db.get(SocialIssueComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    photo_keys = list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.comment_id == comment.id)
    ))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id == comment.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.comment_id == comment.id))
    if comment.is_answer:
        post = await db.get(SocialIssuePost, comment.post_id)
        if post:
            post.resolved_comment_id = None
            if post.status == "resolved":
                post.status = "open"
    await db.delete(comment)
    await db.commit()
    await _best_effort_delete_media(photo_keys)


@router.delete("/issues/posts/{issue_id}", status_code=204)
async def delete_issue_admin(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes an issue post outright (moderation hub, AUT-832). A
    locally-hosted post takedown also fans out via the hub (AUT-902).

    Only posts hosted on this server (origin="local") can be deleted here;
    federated copies are owned by their origin server (AUT-935). A local admin
    moderating an abusive remote post hides it via PATCH /admin/issues/{id}
    instead of deleting the origin's copy."""
    from app.social import federation
    from app.social.federation import FederationUnavailable
    from app.social.models import (
        SocialIssueComment,
        SocialIssueFlag,
        SocialIssuePost,
        SocialPhoto,
        get_server_config,
    )

    post = await db.get(SocialIssuePost, issue_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.origin == "remote":
        raise HTTPException(
            status_code=403,
            detail="Remote posts are hosted on their origin server; "
            "delete them there or hide them locally",
        )
    origin = post.origin
    comment_ids = list(await db.scalars(
        select(SocialIssueComment.id).where(SocialIssueComment.post_id == post.id)
    ))
    media_keys: list[str] = []
    if comment_ids:
        media_keys += list(await db.scalars(
            select(SocialPhoto.file_key).where(SocialPhoto.comment_id.in_(comment_ids))
        ))
        await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id.in_(comment_ids)))
    media_keys += list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.issue_id == post.id)
    ))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.issue_id == post.id))
    await db.execute(delete(SocialIssueComment).where(SocialIssueComment.post_id == post.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.post_id == post.id))
    await db.delete(post)
    await db.commit()
    await _best_effort_delete_media(media_keys)
    if origin == "local":
        cfg = await get_server_config(db)
        if cfg.federation_enabled and cfg.hub_status == "registered" and cfg.hub_server_id:
            try:
                await federation.push_removed(cfg, str(post.id), "issue")
            except (FederationUnavailable, Exception) as exc:
                logger.warning(
                    "social_issue_admin_remove_push_failed", post_id=post.id, error=str(exc)
                )


# --- Community Garage build moderation ---


@router.delete("/social/comments/{comment_id}", status_code=204)
async def delete_build_comment_admin(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a single build comment (moderation hub, AUT-883)."""
    from app.social.models import SocialBuildFlag, SocialComment

    comment = await db.get(SocialComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.comment_id == comment.id))
    await db.delete(comment)
    await db.commit()


@router.delete("/social/posts/{build_id}", status_code=204)
async def delete_build_admin(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Admin deletes a build post outright (moderation hub, AUT-883):
    cascades comments, likes, share scope and flags, best-effort MinIO purge."""
    from app.social.models import (
        SocialBuild,
        SocialBuildFlag,
        SocialComment,
        SocialLike,
        SocialPhoto,
        SocialShareScope,
    )

    build = await db.get(SocialBuild, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Post not found")
    # AUT-997: tombstone deleted builds (local + remote) so a later federation
    # sync cannot re-add them to the feed while the hub still routes them.
    from app.api.v1.social import _tombstone_removed_build

    await _tombstone_removed_build(db, build)
    media_keys = list(await db.scalars(
        select(SocialPhoto.file_key).where(SocialPhoto.build_id == build.id)
    ))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.build_id == build.id))
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id))
    await db.delete(build)
    await db.commit()
    await _best_effort_delete_media(media_keys)


# --- Social bans (AUT-832) ---


@router.post("/users/{user_id}/social-ban")
async def social_ban_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Ban a user from posting in Community Garage and hide all their issue
    posts (moderation hub, AUT-832). Unban restores only what the ban hid —
    posts an admin hid separately stay hidden.

    Scope note: the ban gates every social write (incl. replies/builds) but
    only *hides* issue posts; comments and build posts are removed via the
    hub's per-item delete actions instead (intended, AUT-832 F5)."""
    from app.social.models import SocialIssuePost

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == _admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban your own account")
    user.social_banned = True
    await db.execute(
        update(SocialIssuePost)
        .where(
            SocialIssuePost.author_user_id == user.id,
            SocialIssuePost.status_hidden.is_(False),
        )
        .values(status_hidden=True, hidden_by_ban=True)
    )
    await db.commit()
    return {"message": f"{user.display_name} banned from posting", "social_banned": True}


@router.post("/users/{user_id}/social-unban")
async def social_unban_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Reverse a social ban, restoring only the posts the ban itself hid."""
    from app.social.models import SocialIssuePost

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.social_banned = False
    await db.execute(
        update(SocialIssuePost)
        .where(
            SocialIssuePost.author_user_id == user.id,
            SocialIssuePost.hidden_by_ban.is_(True),
        )
        .values(status_hidden=False, hidden_by_ban=False)
    )
    await db.commit()
    return {"message": f"{user.display_name} unbanned", "social_banned": False}


@router.patch("/issues/{issue_id}")
async def moderate_issue(
    issue_id: str,
    payload: _IssueModerationUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hide/restore an issue post and optionally change its status."""
    from app.api.v1.issues import ISSUE_STATUSES
    from app.social.models import SocialIssuePost

    post = await db.get(SocialIssuePost, issue_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if payload.status_hidden is not None:
        post.status_hidden = payload.status_hidden
    if payload.status is not None:
        if payload.status not in ISSUE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        post.status = payload.status
    await db.commit()
    return {
        "message": "Issue post updated",
        "id": post.id,
        "status_hidden": post.status_hidden,
        "status": post.status,
    }