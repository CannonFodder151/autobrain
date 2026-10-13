"""Social Issues Blog — federation helpers."""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.social import federation
from app.social.federation import FederationUnavailable
from app.social.models import (
    SocialIssueComment,
    SocialIssuePost,
    SocialPhoto,
    get_server_config,
)
from app.social.snapshot import dumps, loads

from app.api.v1.issues.schemas import _parse_remote_created

logger = get_logger(__name__)


async def _push_issue_outbox_safe(
    db: AsyncSession, cfg, post: SocialIssuePost, photo_urls: list[str]
) -> None:
    """Publish a local issue post to the hub so remote servers can pull it.

    The hub relays the whole payload (`/v1/outbox` -> `/v1/inbox`); the
    `type: "issue"` marker lets receivers route it to the issues blog instead
    of the build feed. Failures are logged and never break posting.
    """
    try:
        await federation.push_outbox(cfg, str(post.id), {
            "type": "issue",
            "post_id": post.id,
            "title": post.title,
            "body": post.body,
            "author_display_name": post.author_display_name,
            "server_name": post.server_name,
            "server_id": cfg.hub_server_id,
            "vehicle_snapshot": loads(post.vehicle_snapshot_json) if post.vehicle_snapshot_json else None,
            "tags": list(post.tags or []),
            "status": post.status,
            "resolved_comment_id": post.resolved_comment_id,
            "created_at": post.created_at.isoformat(),
            "photo_urls": photo_urls,
        })
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_issue_outbox_push_failed", post_id=post.id, error=str(exc))


async def _push_issue_event_safe(db: AsyncSession, post: SocialIssuePost, payload: dict) -> None:
    """Fan an issue comment/answer out so remote copies stay in sync."""
    cfg = await get_server_config(db)
    if not cfg.federation_enabled or cfg.hub_status != "registered" or not cfg.hub_server_id:
        return
    origin_post_id = post.remote_post_id if post.origin == "remote" else str(post.id)
    try:
        await federation.push_event(cfg, origin_post_id, "comment", payload)
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_issue_event_push_failed", post_id=post.id, error=str(exc))


async def pull_remote_issue(db: AsyncSession, item: dict, payload: dict) -> None:
    """Insert a federated remote issue post (deduped by origin post id).

    Called from the social feed sync loop; never raises. Remote copies keep
    their origin metadata and the origin's signed photo URLs.
    """
    rid = payload.get("post_id") or payload.get("remote_post_id")
    if not rid:
        return
    existing = await db.scalar(
        select(SocialIssuePost).where(SocialIssuePost.remote_post_id == str(rid))
    )
    if existing:
        return
    db.add(SocialIssuePost(
        author_user_id=None,
        author_display_name=payload.get("author_display_name", "Unknown"),
        server_name=payload.get("server_name"),
        title=payload.get("title", "Untitled"),
        body=payload.get("body", ""),
        vehicle_snapshot_json=dumps(payload.get("vehicle_snapshot") or None)
        if payload.get("vehicle_snapshot") else None,
        tags=[t for t in (payload.get("tags") or []) if isinstance(t, str)],
        status="open",
        origin="remote",
        remote_post_id=str(rid),
        remote_server_id=item.get("origin_server") or payload.get("server_id"),
        photo_urls_json=dumps([u for u in (payload.get("photo_urls") or []) if isinstance(u, str)]),
        created_at=_parse_remote_created(payload.get("created_at")),
        status_hidden=False,
    ))


async def apply_issue_event(db: AsyncSession, event: dict) -> None:
    """Apply a federated issue comment/answer/remove event to the local copy."""
    if not isinstance(event, dict):
        return
    payload = event.get("payload") or {}
    if not isinstance(payload, dict) or payload.get("post_type") != "issue":
        return
    build_id = payload.get("build_id")
    if not build_id:
        return
    if event.get("event_type") == "remove":
        # Takedown (AUT-902): delete the local copy of a removed issue post.
        post = await db.get(SocialIssuePost, str(build_id))
        if not post:
            post = await db.scalar(
                select(SocialIssuePost).where(SocialIssuePost.remote_post_id == str(build_id))
            )
        if not post:
            return
        # Defense-in-depth (AUT-907): never let a hub-relayed `remove` take down
        # a locally-hosted issue post; only this server's own delete path (via
        # hub /v1/remove) can do that.
        if getattr(post, "origin", None) == "local":
            return
        await _purge_issue_post(db, post)
        await db.flush()
        return
    if event.get("event_type") != "comment":
        return
    post = await db.get(SocialIssuePost, build_id)
    if not post:
        post = await db.scalar(
            select(SocialIssuePost).where(SocialIssuePost.remote_post_id == str(build_id))
        )
    if not post or post.status_hidden:
        return
    author = payload.get("author_display_name") or "Unknown"
    server = payload.get("server_name")
    is_answer = bool(payload.get("is_answer"))
    remote_id = payload.get("comment_id")
    if is_answer:
        comment = None
        if remote_id:
            comment = await db.scalar(
                select(SocialIssueComment).where(
                    SocialIssueComment.post_id == post.id,
                    SocialIssueComment.remote_comment_id == str(remote_id),
                )
            )
        if comment is None:
            comment = await db.scalar(
                select(SocialIssueComment)
                .where(
                    SocialIssueComment.post_id == post.id,
                    SocialIssueComment.author_display_name == author,
                    SocialIssueComment.server_name == server,
                    SocialIssueComment.body == payload.get("body", ""),
                )
                .order_by(SocialIssueComment.created_at)
                .limit(1)
            )
        if comment is None:
            return
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
        return
    if remote_id:
        exists = await db.scalar(
            select(SocialIssueComment).where(
                SocialIssueComment.post_id == post.id,
                SocialIssueComment.remote_comment_id == str(remote_id),
            )
        )
        if exists:
            return
    db.add(SocialIssueComment(
        post_id=post.id,
        author_user_id=None,
        author_display_name=author,
        server_name=server,
        body=payload.get("body", ""),
        remote_comment_id=str(remote_id) if remote_id else None,
    ))


async def _purge_issue_post(db: AsyncSession, post: SocialIssuePost) -> None:
    """Hard-delete an issue post + children (photos, comments, flags)."""
    from sqlalchemy import delete

    comment_ids = list(await db.scalars(
        select(SocialIssueComment.id).where(SocialIssueComment.post_id == post.id)
    ))
    if comment_ids:
        await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id.in_(comment_ids)))
    await db.execute(delete(SocialPhoto).where(SocialPhoto.issue_id == post.id))
    await db.execute(delete(SocialIssueComment).where(SocialIssueComment.post_id == post.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.post_id == post.id))
    await db.delete(post)