"""Social Issues Blog — post CRUD endpoints."""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.ownership import get_accessible_vehicle
from app.services.search import _escape_like
from app.social.media import signed_url
from app.social.models import (
    SocialIssueComment,
    SocialIssueFlag,
    SocialIssuePost,
    SocialPhoto,
    get_server_config,
)
from app.social.rate_limit import social_rate_limit, social_user_rate_limit
from app.social.snapshot import dumps, loads
from app.social.tags import TAG_VOCABULARY, detect_tags

from app.api.v1.issues.schemas import (
    ISSUE_STATUSES,
    MAX_TITLE,
    MAX_BODY,
    MAX_COMMENT,
    MAX_REASON,
    MAX_PHOTOS,
    _LIST_LIMIT_MAX,
    IssueCreate,
    IssueUpdate,
    _plaintext,
    _vehicle_snapshot,
    _encode_cursor,
    _decode_cursor,
    _tags_contains,
)
from app.api.v1.issues.federation import (
    _push_issue_outbox_safe,
    _push_issue_event_safe,
    _purge_issue_post,
)

logger = get_logger(__name__)


router = APIRouter(prefix="/social/issues", tags=["social-issues"])


async def _get_visible(db: AsyncSession, post_id: str) -> SocialIssuePost:
    post = await db.get(SocialIssuePost, post_id)
    if not post or post.status_hidden:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


async def _comment_count(db: AsyncSession, post_id: str) -> int:
    return (await db.scalar(
        select(func.count()).select_from(SocialIssueComment).where(
            SocialIssueComment.post_id == post_id
        )
    )) or 0


async def _photo_urls(db: AsyncSession, post: SocialIssuePost) -> list[str]:
    if post.origin == "remote":
        if not post.photo_urls_json:
            return []
        try:
            urls = json.loads(post.photo_urls_json)
        except (TypeError, ValueError):
            return []
        return [u for u in urls if isinstance(u, str)]
    rows = list(await db.scalars(
        select(SocialPhoto)
        .where(SocialPhoto.issue_id == post.id)
        .order_by(SocialPhoto.position, SocialPhoto.created_at)
    ))
    urls: list[str] = []
    for p in rows:
        try:
            urls.append(await signed_url(p.file_key))
        except Exception:
            continue
    return urls


async def _comment_photo_url(db: AsyncSession, comment_id: str) -> str | None:
    p = await db.scalar(
        select(SocialPhoto)
        .where(SocialPhoto.comment_id == comment_id)
        .order_by(SocialPhoto.created_at)
        .limit(1)
    )
    if p is None:
        return None
    try:
        return await signed_url(p.file_key)
    except Exception:
        return None


async def _serialize(db: AsyncSession, post: SocialIssuePost, viewer: User) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author_display_name": post.author_display_name,
        "server_name": post.server_name,
        "origin": post.origin,
        "tags": list(post.tags or []),
        "status": post.status,
        "resolved_comment_id": post.resolved_comment_id,
        "vehicle_snapshot": loads(post.vehicle_snapshot_json) if post.vehicle_snapshot_json else None,
        "comment_count": await _comment_count(db, post.id),
        "photos": await _photo_urls(db, post),
        "photo_ids": list(await db.scalars(
            select(SocialPhoto.id).where(SocialPhoto.issue_id == post.id)
        )) if viewer.id == post.author_user_id else [],
        "is_mine": viewer.id == post.author_user_id,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


@router.get("")
async def list_issues(
    limit: int = Query(default=20, ge=1, le=_LIST_LIMIT_MAX),
    cursor: str | None = Query(default=None, max_length=512),
    tag: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=150),
    mine: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(30)),
) -> dict:
    from app.api.v1.social import _sync_federation

    await _sync_federation(db)
    await db.commit()
    if tag and tag not in TAG_VOCABULARY:
        raise HTTPException(status_code=400, detail=f"Unknown tag: {tag}")
    if status and status not in ISSUE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {status}")

    stmt = select(SocialIssuePost).where(SocialIssuePost.status_hidden.is_(False))
    if mine:
        stmt = stmt.where(SocialIssuePost.author_user_id == _user.id)
    if tag:
        stmt = stmt.where(await _tags_contains(db, tag))
    if status:
        stmt = stmt.where(SocialIssuePost.status == status)
    if q and q.strip():
        needle = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                SocialIssuePost.title.ilike(needle, escape="\\"),
                SocialIssuePost.body.ilike(needle, escape="\\"),
            )
        )
    if cursor:
        c_created, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                SocialIssuePost.created_at < c_created,
                and_(
                    SocialIssuePost.created_at == c_created,
                    SocialIssuePost.id < c_id,
                ),
            )
        )
    rows = list((
        await db.scalars(
            stmt.order_by(SocialIssuePost.created_at.desc(), SocialIssuePost.id.desc())
            .limit(limit + 1)
        )
    ).all())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return {
        "items": [await _serialize(db, p, _user) for p in page],
        "next_cursor": next_cursor,
    }


@router.post("", status_code=201)
async def create_issue(
    payload: IssueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("issues-create", 5)),
) -> dict:
    title = _plaintext(payload.title).strip()
    body = _plaintext(payload.body).strip()
    if not title or not body:
        raise HTTPException(status_code=422, detail="Title and body are required")

    vehicle = None
    snapshot = None
    if payload.vehicle_id:
        vehicle = await get_accessible_vehicle(db, payload.vehicle_id, user)
        snapshot = _vehicle_snapshot(vehicle)
    cfg = await get_server_config(db)
    post = SocialIssuePost(
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        title=title,
        body=body,
        vehicle_snapshot_json=dumps(snapshot) if snapshot is not None else None,
        tags=detect_tags(title, body, snapshot),
        origin="local",
        status="open",
    )
    db.add(post)
    await db.flush()
    if payload.photo_ids:
        photos = list(await db.scalars(
            select(SocialPhoto).where(
                SocialPhoto.id.in_(set(payload.photo_ids)),
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.build_id.is_(None),
                SocialPhoto.issue_id.is_(None),
            )
        ))
        if len({p.id for p in photos}) != len(set(payload.photo_ids)):
            raise HTTPException(
                status_code=422,
                detail="One or more photos are invalid (wrong owner or already attached)",
            )
        for photo in photos:
            photo.issue_id = post.id
    await db.commit()
    photo_urls: list[str] = []
    if payload.photo_ids:
        for photo in photos:
            try:
                photo_urls.append(await signed_url(photo.file_key))
            except Exception:
                continue
    if post.origin == "local" and cfg.federation_enabled and cfg.hub_status == "registered":
        await _push_issue_outbox_safe(db, cfg, post, photo_urls)
    from app.workers.tasks import queue_embedding

    queue_embedding("issue", str(post.id))
    return await _serialize(db, post, user)


@router.get("/{post_id}")
async def get_issue(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(30)),
) -> dict:
    post = await _get_visible(db, post_id)
    comments = list(await db.scalars(
        select(SocialIssueComment)
        .where(SocialIssueComment.post_id == post.id)
        .order_by(SocialIssueComment.created_at)
    ))
    return {
        **await _serialize(db, post, user),
        "comments": [
            {
                "id": c.id,
                "author_display_name": c.author_display_name,
                "server_name": c.server_name,
                "body": c.body,
                "photo": await _comment_photo_url(db, c.id),
                "is_answer": c.is_answer,
                "is_mine": user.id == c.author_user_id,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ],
    }


@router.patch("/{post_id}")
async def update_issue(
    post_id: str,
    payload: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
) -> dict:
    post = await _get_visible(db, post_id)
    if post.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    updates = payload.model_dump(exclude_unset=True)
    title = _plaintext(updates["title"]).strip() if updates.get("title") is not None else None
    body = _plaintext(updates["body"]).strip() if updates.get("body") is not None else None
    if title is not None:
        if not title:
            raise HTTPException(status_code=422, detail="Title cannot be empty")
        post.title = title
    if body is not None:
        if not body:
            raise HTTPException(status_code=422, detail="Body cannot be empty")
        post.body = body
    if updates.get("status") is not None:
        status = updates["status"]
        if status not in ISSUE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        post.status = status
    snapshot = None
    if post.vehicle_snapshot_json:
        snapshot = loads(post.vehicle_snapshot_json)
    post.tags = detect_tags(post.title, post.body, snapshot)
    await db.commit()
    if title is not None or body is not None:
        from app.workers.tasks import queue_embedding

        queue_embedding("issue", str(post.id))
    await db.refresh(post)
    return await _serialize(db, post, user)


@router.delete("/{post_id}", status_code=204)
async def delete_issue(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
) -> None:
    post = await db.get(SocialIssuePost, post_id)
    if not post or post.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    origin = post.origin
    await _purge_issue_post(db, post)
    await db.commit()
    if origin == "local":
        cfg = await get_server_config(db)
        if cfg.federation_enabled and cfg.hub_status == "registered" and cfg.hub_server_id:
            try:
                from app.social import federation
                await federation.push_removed(cfg, str(post.id), "issue")
            except (federation.FederationUnavailable, Exception) as exc:
                logger.warning("social_issue_remove_push_failed", post_id=post.id, error=str(exc))