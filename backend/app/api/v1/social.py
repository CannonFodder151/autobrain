"""Community Garage social routes (AUT-294 rev 7, AUT-332).

Feature gate: every route 403s with "Disabled by your admin" when the feature
toggle is off, and requires premium entitlement (rev 4). Federation off = the
feed still works, local builds only.
"""

import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.social import federation
from app.social.federation import FederationUnavailable
from app.social.media import MAX_UPLOAD_BYTES, MediaError, read_upload, signed_url, upload_photo
from app.social.rate_limit import social_rate_limit, social_user_rate_limit
from app.social.models import (
    SocialBuild,
    SocialBuildFlag,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot, dumps, loads

logger = get_logger(__name__)

_INBOX_SYNC_TTL_SECONDS = 60


async def require_social_feature(db: AsyncSession = Depends(get_db)) -> None:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        raise HTTPException(status_code=403, detail="Disabled by your admin")


router = APIRouter(
    prefix="/social",
    tags=["social"],
    dependencies=[Depends(require_social_feature)],
)


class ShareScopeIn(BaseModel):
    allow_photos: bool = True
    allow_specs: bool = True
    allow_mods: bool = True
    allow_odometer: bool = False
    allow_notes: bool = False


class PostCreate(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=36)
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=1000)
    share_scope: ShareScopeIn = ShareScopeIn()
    photo_ids: list[str] = Field(default_factory=list, max_length=15)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class PostUpdate(BaseModel):
    """Full build edit (AUT-675): title, caption, photo order/swap and scope.

    `None` means "leave unchanged"; pass empty strings/lists to clear.
    """
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=1000)
    photo_ids: list[str] | None = Field(default=None, max_length=12)
    share_scope: ShareScopeIn | None = None


class FlagIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


def _plaintext(value: str) -> str:
    """Strip control characters so stored reasons never carry markup or raw
    control codes (mirror of the issues-blog helper)."""
    return "".join(c for c in value if c >= " " or c in "\n\t")


async def _like_count(db: AsyncSession, build_id: str) -> int:
    return (await db.scalar(
        select(func.count()).select_from(SocialLike).where(SocialLike.build_id == build_id)
    )) or 0


async def _comment_count(db: AsyncSession, build_id: str) -> int:
    return (await db.scalar(
        select(func.count()).select_from(SocialComment).where(SocialComment.build_id == build_id)
    )) or 0


async def _serialize(db: AsyncSession, build: SocialBuild, viewer: User | None) -> dict:
    snapshot = loads(build.snapshot_json)
    photo_keys = list(snapshot.get("photo_keys", []))
    photo_ids: list[str] = []
    scope = await db.scalar(
        select(SocialShareScope).where(SocialShareScope.build_id == build.id)
    )
    share_scope = {
        "allow_photos": scope.allow_photos if scope else True,
        "allow_specs": scope.allow_specs if scope else True,
        "allow_mods": scope.allow_mods if scope else True,
        "allow_odometer": scope.allow_odometer if scope else False,
        "allow_notes": scope.allow_notes if scope else False,
    }
    if build.origin in ("local", "demo") and build.vehicle_id:
        vehicle = await db.get(Vehicle, build.vehicle_id)
        if vehicle:
            photos = list(await db.scalars(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.position, SocialPhoto.created_at)
            ))
            snapshot = await build_snapshot(db, vehicle, scope, [p.file_key for p in photos])
            photo_keys = list(snapshot.get("photo_keys", []))
            photo_ids = [p.id for p in photos]
    photos: list[str] = []
    for key in photo_keys:
        try:
            photos.append(await signed_url(key))
        except Exception:
            continue
    liked = viewer is not None and (
        await db.scalar(
            select(SocialLike).where(
                SocialLike.build_id == build.id,
                SocialLike.author_user_id == viewer.id,
            )
        )
    ) is not None
    is_author = viewer is not None and build.author_user_id is not None and viewer.id == build.author_user_id
    return {
        "id": build.id,
        "title": build.title,
        "caption": build.caption,
        "author_display_name": build.remote_author_display_name or build.author_display_name,
        "server_name": build.server_name,
        "origin": build.origin,
        "snapshot": snapshot,
        "photos": photos,
        "photo_ids": photo_ids if is_author else [],
        "share_scope": share_scope,
        "like_count": await _like_count(db, build.id),
        "liked_by_me": liked,
        "comment_count": await _comment_count(db, build.id),
        "created_at": build.created_at.isoformat(),
    }


async def _get_published(db: AsyncSession, build_id: str) -> SocialBuild:
    build = await db.get(SocialBuild, build_id)
    if not build or build.status != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    return build


async def _sync_federation(db: AsyncSession) -> None:
    """Pull remote builds + like/comment events from the hub when due.

    Errors never break the feed. Events (comment/like) are applied to the
    matching local copy (AUT-462 FD-1); remote builds keep their author and
    caption metadata (FD-2).
    """
    cfg = await get_server_config(db)
    if not cfg.federation_enabled or cfg.hub_status not in ("registered", "pending") or not cfg.hub_server_id:
        return
    # AUT-731: a `pending` registration can only federate once the hub operator
    # approves it (AUT-525). Poll the hub's public status endpoint so the
    # server self-heals into `registered` without a manual re-register.
    if cfg.hub_status == "pending":
        try:
            info = await federation.get_server_status(cfg)
        except FederationUnavailable as exc:
            logger.warning("social_federation_status_check_failed", error=str(exc))
            return
        if info.get("status") in ("approved", "registered"):
            cfg.hub_status = "registered"
            await db.flush()
        else:
            return
    last_sync = cfg.last_inbox_sync
    if last_sync is not None:
        if last_sync.tzinfo is None:  # sqlite stores tz-aware columns as naive
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last_sync < timedelta(seconds=_INBOX_SYNC_TTL_SECONDS):
            return
    try:
        remote_builds = await federation.pull_inbox(cfg)
        event_data = await federation.pull_events(cfg, cfg.last_event_sync or 0)
    except FederationUnavailable as exc:
        logger.warning("social_federation_sync_failed", error=str(exc))
        return
    events = event_data.get("events", []) if isinstance(event_data, dict) else []
    for item in remote_builds:
        if not isinstance(item, dict):
            continue
        build = item.get("build") or item
        if not isinstance(build, dict):
            continue
        if build.get("type") == "issue":
            # Federated Issues Blog posts (AUT-756) live in the blog list, not
            # the build feed. Lazy import avoids the issues->social import cycle.
            from app.api.v1.issues import pull_remote_issue

            await pull_remote_issue(db, item, build)
            continue
        rid = build.get("remote_build_id") or build.get("build_id")
        if not rid:
            continue
        existing = await db.scalar(
            select(SocialBuild).where(SocialBuild.remote_build_id == str(rid))
        )
        if existing:
            continue
        db.add(SocialBuild(
            author_display_name=build.get("author_display_name", "Unknown"),
            remote_author_display_name=build.get("author_display_name"),
            server_name=build.get("server_name"),
            title=build.get("title", "Untitled build"),
            caption=build.get("caption"),
            origin="remote",
            remote_build_id=str(rid),
            remote_server_id=item.get("origin_server") or build.get("server_id"),
            snapshot_json=dumps(build.get("snapshot") or {}),
        ))
    for event in events:
        await _apply_event(db, event)
    cfg.last_inbox_sync = datetime.now(timezone.utc)
    if event_data:
        cursor = event_data.get("next_cursor")
        if cursor is not None:
            try:
                cfg.last_event_sync = int(cursor)
            except (TypeError, ValueError):
                logger.warning("social_event_cursor_invalid", cursor=cursor)
    await db.flush()


async def _apply_event(db: AsyncSession, event: dict) -> None:
    """Apply a federated comment/like event to the matching local build copy."""
    if not isinstance(event, dict):
        return
    if event.get("event_type") not in ("comment", "like"):
        return
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        return
    if payload.get("post_type") == "issue":
        # Federated Issues Blog comment/answer event (AUT-756).
        from app.api.v1.issues import apply_issue_event

        await apply_issue_event(db, event)
        return
    build_id = payload.get("build_id")
    if not build_id:
        return
    build = await db.get(SocialBuild, build_id)
    if not build:
        build = await db.scalar(
            select(SocialBuild).where(SocialBuild.remote_build_id == str(build_id))
        )
    if not build or build.status != "published":
        return
    author = payload.get("author_display_name") or "Unknown"
    server = payload.get("server_name")
    if event["event_type"] == "comment":
        db.add(SocialComment(
            build_id=build.id,
            author_display_name=author,
            server_name=server,
            body=payload.get("body", ""),
        ))
        return
    # like: delete-then-(maybe)-insert keeps toggles idempotent per remote author.
    liked = bool(payload.get("liked"))
    like = await db.scalar(select(SocialLike).where(
        SocialLike.build_id == build.id,
        SocialLike.author_display_name == author,
        SocialLike.server_name == server,
    ))
    if liked and like is None:
        db.add(SocialLike(
            build_id=build.id,
            author_display_name=author,
            server_name=server,
        ))
    elif not liked and like is not None:
        await db.delete(like)


async def _push_outbox_safe(cfg, build: SocialBuild, snapshot: dict, photo_keys: list[str]) -> None:
    """Push a local build (metadata + photos) so remote copies keep author info."""
    try:
        await federation.push_outbox(cfg, build.id, {
            "build_id": build.id,
            "title": snapshot.get("title"),
            "caption": build.caption,
            "author_display_name": build.author_display_name,
            "server_name": build.server_name or cfg.server_name,
            "snapshot": snapshot,
            "photo_urls": [await signed_url(k) for k in photo_keys],
        })
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_outbox_push_failed", build_id=build.id, error=str(exc))


@router.get("/feed")
async def feed(
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=120),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(24)),
) -> dict:
    await _sync_federation(db)
    await db.commit()
    stmt = select(SocialBuild).where(SocialBuild.status == "published")
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            SocialBuild.title.ilike(needle)
            | SocialBuild.caption.ilike(needle)
            | SocialBuild.author_display_name.ilike(needle)
            | SocialBuild.server_name.ilike(needle)
        )
    rows = await db.scalars(
        stmt.order_by(SocialBuild.created_at.desc()).limit(limit)
    )
    return {"items": [await _serialize(db, b, user) for b in rows]}


@router.get("/my-posts")
async def my_posts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
    _rl: None = Depends(social_rate_limit(24)),
) -> dict:
    """The caller's own builds (My Builds tab, AUT-501). Local-only; remote
    copies have no local author."""
    rows = await db.scalars(
        select(SocialBuild)
        .where(
            SocialBuild.status == "published",
            SocialBuild.author_user_id == user.id,
        )
        .order_by(SocialBuild.created_at.desc())
        .limit(200)
    )
    return {"items": [await _serialize(db, b, user) for b in rows]}


@router.post("/posts", status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    vehicle = await get_accessible_vehicle(db, payload.vehicle_id, user)
    scope = SocialShareScope(**payload.share_scope.model_dump())
    photo_keys: list[str] = []
    photos: list[SocialPhoto] = []
    if payload.photo_ids:
        photos = list(await db.scalars(
            select(SocialPhoto).where(
                SocialPhoto.id.in_(payload.photo_ids),
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.build_id.is_(None),
                SocialPhoto.issue_id.is_(None),
            )
        ))
        photo_keys = [p.file_key for p in photos]
    snapshot = await build_snapshot(db, vehicle, scope, photo_keys)
    cfg = await get_server_config(db)
    build = SocialBuild(
        vehicle_id=vehicle.id,
        author_user_id=user.id,
        author_display_name=user.display_name,
        server_name=cfg.server_name,
        title=payload.title.strip() if payload.title and payload.title.strip() else snapshot["title"],
        caption=payload.caption,
        origin="local",
        snapshot_json=dumps(snapshot),
    )
    db.add(build)
    await db.flush()
    scope.build_id = build.id
    db.add(scope)
    for photo in photos:
        photo.build_id = build.id
    if build.origin == "local":
        await add_event(
            db, vehicle.id, "mod", f"Shared build: {build.title}",
            date.today(), None, None, build.id,
        )
    await db.commit()
    if build.origin == "local" and cfg.federation_enabled and cfg.hub_status == "registered":
        await _push_outbox_safe(cfg, build, snapshot, photo_keys)
    return await _serialize(db, build, user)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await _get_published(db, post_id)
    return await _serialize(db, build, user)


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: str,
    payload: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    """Edit a build (AUT-675): name/title, caption, photo reorder/upload/remove
    and share scope. Ownership check matches delete: 404 for non-owners so
    posts cannot be probed (PW-8)."""
    build = await _get_published(db, post_id)
    if build.author_user_id != user.id:
        raise HTTPException(status_code=404, detail="Post not found")
    if build.origin == "remote":
        raise HTTPException(
            status_code=400, detail="Remote builds can only be edited on their origin server"
        )
    fields = payload.model_fields_set
    if "title" in fields:
        build.title = payload.title.strip() if payload.title and payload.title.strip() else build.title
    if "caption" in fields and payload.caption is not None:
        build.caption = payload.caption or None
    scope = await db.scalar(
        select(SocialShareScope).where(SocialShareScope.build_id == build.id)
    )
    if "share_scope" in fields and payload.share_scope is not None:
        if scope is None:
            scope = SocialShareScope(
                build_id=build.id, **payload.share_scope.model_dump())
            db.add(scope)
        else:
            for key, value in payload.share_scope.model_dump().items():
                setattr(scope, key, value)
    if "photo_ids" in fields and payload.photo_ids is not None:
        if len(payload.photo_ids) > 12 or len(set(payload.photo_ids)) != len(payload.photo_ids):
            raise HTTPException(status_code=400, detail="Invalid photo list")
        photos = list(await db.scalars(
            select(SocialPhoto).where(
                SocialPhoto.id.in_(payload.photo_ids),
                SocialPhoto.uploader_user_id == user.id,
                SocialPhoto.issue_id.is_(None),
                or_(SocialPhoto.build_id.is_(None), SocialPhoto.build_id == build.id),
            )
        ))
        by_id = {p.id: p for p in photos}
        if len(by_id) != len(payload.photo_ids):
            raise HTTPException(
                status_code=400, detail="Some photos could not be used")
        keep = set(payload.photo_ids)
        current = list(await db.scalars(
            select(SocialPhoto).where(SocialPhoto.build_id == build.id)))
        for photo in current:
            if photo.id not in keep:
                photo.build_id = None  # back to the user's unassigned pool
        for position, photo_id in enumerate(payload.photo_ids):
            photo = by_id[photo_id]
            photo.build_id = build.id
            photo.position = position
    snapshot = None
    photo_keys = []
    if build.vehicle_id:
        vehicle = await db.get(Vehicle, build.vehicle_id)
        if vehicle:
            photos = list(await db.scalars(
                select(SocialPhoto).where(SocialPhoto.build_id == build.id).order_by(SocialPhoto.position, SocialPhoto.created_at)
            ))
            snapshot = await build_snapshot(db, vehicle, scope, [p.file_key for p in photos])
            build.snapshot_json = dumps(snapshot)
            photo_keys = [p.file_key for p in photos]
    cfg = await get_server_config(db)
    await db.commit()
    if build.origin == "local" and cfg.federation_enabled and cfg.hub_status == "registered":
        await _push_outbox_safe(cfg, build, snapshot, photo_keys)
    return await _serialize(db, build, user)


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


@router.post("/posts/{post_id}/share-link")
async def create_share_link(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    build = await _get_published(db, post_id)
    if build.origin == "remote":
        raise HTTPException(
            status_code=400,
            detail="Share links for remote builds resolve on their origin server",
        )
    if not build.share_token:
        build.share_token = secrets.token_urlsafe(16)
        await db.commit()
    return {"token": build.share_token, "url": f"/social/share/{build.share_token}"}


@router.get("/share/{token}")
async def resolve_share_link(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
) -> dict:
    build = await db.scalar(select(SocialBuild).where(SocialBuild.share_token == token))
    if not build or build.status != "published":
        raise HTTPException(status_code=404, detail="Build not found")
    return await _serialize(db, build, user)

def _reject_oversized_content_length(request: Request) -> None:
    """Return 413 on a declared Content-Length past the cap before any body read.

    Must resolve before the UploadFile dependency so the multipart body is never
    parsed/buffered for oversized uploads. Missing or lying Content-Length is
    covered by the bounded read_upload() inside the handler.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")


@router.post("/uploads", status_code=201)
async def upload(
    _size_guard: None = Depends(_reject_oversized_content_length),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    try:
        data = await read_upload(file)
        key, url, width, height = await upload_photo(user.id, data, file.content_type)
    except MediaError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    photo = SocialPhoto(uploader_user_id=user.id, file_key=key, width=width, height=height)
    db.add(photo)
    await db.commit()
    return {"id": photo.id, "url": url}


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
) -> None:
    """Unshare a build (takedown propagates locally)."""
    build = await _get_published(db, post_id)
    if build.author_user_id != user.id:
        # 404, not 403, so non-owners cannot tell a post exists (PW-8).
        raise HTTPException(status_code=404, detail="Post not found")
    # Bulk deletes/update run immediately, so every child row is gone before the
    # parent DELETE — an ORM db.delete loop does not order child deletes first
    # (no relationship/cascade) and 500s on the FK (AUT-703, AUT-762).
    await db.execute(
        update(SocialPhoto)
        .where(SocialPhoto.build_id == build.id)
        .values(build_id=None)
    )
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.execute(delete(SocialBuildFlag).where(SocialBuildFlag.build_id == build.id))
    await db.delete(build)
    await db.commit()


@router.post("/posts/{post_id}/flag", status_code=201)
async def flag_build(
    post_id: str,
    payload: FlagIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(5)),
    _user_rl: None = Depends(social_user_rate_limit("builds-flag", 5)),
) -> dict:
    """Report a build post (AUT-883 moderation queue). Deduped per user."""
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
    """Report a comment on a build (AUT-883 moderation queue)."""
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
