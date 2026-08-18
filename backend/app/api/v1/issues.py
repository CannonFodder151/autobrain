"""Community Garage issues blog routes (AUT-627).

Blog-style help board: owners post car issues, other owners reply, the author
(or a helper) can pin the answer and resolve the post. Deterministic-first:
tags come from a fixed vocabulary, search is keyword+vector hybrid, no AI is
invoked for authoring, answers, or moderation.

Federation (AUT-756): issue posts are pushed to the hub outbox on create and
comments/answers fan out via events, mirroring the build path. Remote posts are
stored as `origin="remote"` copies carrying the origin's signed photo URLs.

Security: premium entitlement server-side on every route (free accounts are
locked out); plaintext only (control chars stripped, no HTML rendering);
LIKE injection via `_escape_like`; flags capped per user per post + rate
limited; hidden posts excluded from browse; 404-for-non-owners so posts cannot
be probed (PW-8 pattern).
"""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Text, and_, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.api.v1.social import require_social_feature
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.ownership import get_accessible_vehicle
from app.services.search import _escape_like
from app.social import federation
from app.social.federation import FederationUnavailable
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

logger = get_logger(__name__)

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


async def _photo_urls(db: AsyncSession, post: SocialIssuePost) -> list[str]:
    """Display photo URLs for an issue post.

    Local/demo posts resolve MinIO presigns from the attached photos; remote
    copies return the signed URLs their origin server published (AUT-756).
    """
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
        "photos": await _photo_urls(db, post),
        # F1 pattern: photo ids only to the author, never leaked to viewers.
        "photo_ids": list(await db.scalars(
            select(SocialPhoto.id).where(SocialPhoto.issue_id == post.id)
        )) if viewer.id == post.author_user_id else [],
        "is_mine": viewer.id == post.author_user_id,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


# ── Federation (AUT-756) ────────────────────────────────────────────────────

def _parse_remote_created(value: str | None) -> datetime:
    """Parse an origin's ISO created_at, tolerating a trailing Z."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


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
    mine: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(30)),
) -> dict:
    """Blog list — reverse-chronological with keyset cursor pagination.

    `mine=true` filters to the caller's own posts ("My Issues", AUT-832).
    """
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


@router.delete("/{post_id}", status_code=204)
async def delete_issue(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
) -> None:
    """Delete the author's own post (cascades comments + flags, takedown fans
    out via the hub)."""
    post = await db.get(SocialIssuePost, post_id)
    if not post or post.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    origin = post.origin
    await _purge_issue_post(db, post)
    await db.commit()
    # Takedown fan-out for locally-hosted posts only (AUT-902).
    if origin == "local":
        cfg = await get_server_config(db)
        if cfg.federation_enabled and cfg.hub_status == "registered" and cfg.hub_server_id:
            try:
                await federation.push_removed(cfg, str(post.id), "issue")
            except (FederationUnavailable, Exception) as exc:
                logger.warning("social_issue_remove_push_failed", post_id=post.id, error=str(exc))


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
