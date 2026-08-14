"""Community Garage issues blog routes (AUT-627).

Blog-style help board: owners post car issues, other owners reply, the author
(or a helper) can pin the answer and resolve the post. Deterministic-first:
tags come from a fixed vocabulary, search is keyword+vector hybrid, no AI is
invoked for authoring, answers, or moderation.

Security: premium entitlement server-side on every route (free accounts are
locked out); plaintext only (control chars stripped, no HTML rendering);
LIKE injection via `_escape_like`; flags capped per user per post + rate
limited; hidden posts excluded from browse; 404-for-non-owners so posts cannot
be probed (PW-8 pattern).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.ownership import get_accessible_vehicle
from app.services.search import _escape_like
from app.social.models import (
    SocialIssueComment,
    SocialIssueFlag,
    SocialIssuePost,
    SocialPhoto,
    get_server_config,
)
from app.social.media import signed_url
from app.social.rate_limit import social_rate_limit, social_user_rate_limit
from app.social.snapshot import dumps, loads
from app.social.tags import TAG_VOCABULARY, detect_tags
from app.api.v1.social import require_social_feature

router = APIRouter(
    prefix="/social/issues",
    tags=["social-issues"],
    dependencies=[Depends(require_social_feature)],
)

ISSUE_STATUSES = {"open", "answered", "resolved"}

MAX_TITLE = 150
MAX_BODY = 4000
MAX_COMMENT = 2000
MAX_REASON = 200
MAX_PHOTOS = 4
_LIST_LIMIT_MAX = 50


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    body: str = Field(min_length=1, max_length=MAX_BODY)
    vehicle_id: str | None = Field(default=None, max_length=36)
    photo_ids: list[str] = Field(default_factory=list, max_length=MAX_PHOTOS)


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    body: str | None = Field(default=None, min_length=1, max_length=MAX_BODY)
    status: str | None = Field(default=None)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_COMMENT)
    photo_id: str | None = Field(default=None, max_length=36)


class FlagIn(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON)


def _plaintext(value: str) -> str:
    """Strip control characters so bodies are render-safe plaintext (no XSS).

    Only newlines survive; tabs/other C0 controls become spaces.
    """
    return "".join(
        ch if ch.isprintable() else ("\n" if ch == "\n" else " ")
        for ch in value
    )


def _vehicle_snapshot(vehicle: Vehicle) -> dict:
    return {k: getattr(vehicle, k) for k in ("make", "model", "year") if getattr(vehicle, k)}


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


async def _photo_urls(db: AsyncSession, post_id: str) -> list[str]:
    rows = list(await db.scalars(
        select(SocialPhoto)
        .where(SocialPhoto.issue_id == post_id)
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
    """A reply's single photo (AUT-736). Returns None when there is none."""
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
        "vehicle_snapshot": loads(post.vehicle_snapshot_json),
        "comment_count": await _comment_count(db, post.id),
        "photos": await _photo_urls(db, post.id),
        # F1 pattern: photo ids only to the author, never leaked to viewers.
        "photo_ids": list(await db.scalars(
            select(SocialPhoto.id).where(SocialPhoto.issue_id == post.id)
        )) if viewer.id == post.author_user_id else [],
        "is_mine": viewer.id == post.author_user_id,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


async def _tags_contains(db: AsyncSession, tag: str) -> Any:
    """Portable tag filter: native array containment on postgres, JSON-text
    LIKE elsewhere (sqlite test engines). `tag` is vocab-validated upstream.
    Cast to plain Text so the TypeDecorator's JSON bind processing never
    applies to the LIKE pattern."""
    if db.get_bind().dialect.name == "postgresql":
        return text(":t = ANY(social_issue_posts.tags)").bindparams(t=tag)
    return cast(SocialIssuePost.tags, Text).like(f'%"{tag}"%')


def _encode_cursor(created_at: datetime, post_id: str) -> str:
    import base64
    import json

    raw = json.dumps({"c": created_at.isoformat(), "i": post_id}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    import base64
    import json

    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(raw["c"]), str(raw["i"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid cursor")


@router.get("")
async def list_issues(
    limit: int = Query(default=20, ge=1, le=_LIST_LIMIT_MAX),
    cursor: str | None = Query(default=None, max_length=512),
    tag: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=150),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(30)),
) -> dict:
    """Blog list — reverse-chronological with keyset cursor pagination."""
    if tag and tag not in TAG_VOCABULARY:
        raise HTTPException(status_code=400, detail=f"Unknown tag: {tag}")
    if status and status not in ISSUE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {status}")

    stmt = select(SocialIssuePost).where(SocialIssuePost.status_hidden.is_(False))
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
    return {"id": comment.id, "is_answer": True, "status": post.status}


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


@router.delete("/{post_id}", status_code=204)
async def delete_issue(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
) -> None:
    """Delete the author's own post (cascades comments + flags)."""
    post = await db.get(SocialIssuePost, post_id)
    if not post or post.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    from sqlalchemy import delete

    comment_ids = list(await db.scalars(
        select(SocialIssueComment.id).where(SocialIssueComment.post_id == post.id)
    ))
    await db.execute(delete(SocialIssueComment).where(SocialIssueComment.post_id == post.id))
    await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.post_id == post.id))
    if comment_ids:
        await db.execute(delete(SocialPhoto).where(SocialPhoto.comment_id.in_(comment_ids)))
    for photo in list(await db.scalars(
        select(SocialPhoto).where(SocialPhoto.issue_id == post.id)
    )):
        await db.delete(photo)
    await db.delete(post)
    await db.commit()
