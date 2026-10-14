"""Shared helpers for social API routes."""

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
    SocialRemoteTombstone,
    SocialShareScope,
    get_server_config,
)
from app.social.snapshot import build_snapshot, dumps, loads

logger = get_logger(__name__)

_INBOX_SYNC_TTL_SECONDS = 60


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


class ReportIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class PostUpdate(BaseModel):
    """Full build edit (AUT-675): title, caption, photo order/swap and scope.

    Omitted fields stay unchanged; pass `null` or an empty string to clear.
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


async def _purge_build(db: AsyncSession, build: SocialBuild) -> None:
    """Hard-delete a build + children (photos released, comments/likes/scope
    removed). Bulk deletes run immediately so the parent DELETE never hits an
    FK (AUT-703, AUT-762)."""
    await db.execute(
        update(SocialPhoto)
        .where(SocialPhoto.build_id == build.id)
        .values(build_id=None)
    )
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.delete(build)


async def _tombstone_removed_build(db: AsyncSession, build: SocialBuild) -> None:
    """Record a durable removal so a later federation sync cannot re-add a
    deleted build to the feed while the hub still routes its post event.

    Remote copies tombstone their `remote_build_id` (AUT-910); local builds
    tombstone their own id — the routed key for origin-created builds — so an
    author/admin delete of a local post stays gone from its origin feed
    (AUT-997). Requires an active hub registration, else the tombstone is
    unnecessary and would linger.
    """
    if build.origin == "remote" and build.remote_build_id:
        await db.merge(SocialRemoteTombstone(remote_build_id=build.remote_build_id))
        return
    if build.origin != "local":
        return
    cfg = await get_server_config(db)
    if cfg.federation_enabled and cfg.hub_status in ("registered", "pending") and cfg.hub_server_id:
        await db.merge(SocialRemoteTombstone(remote_build_id=build.id))


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
    # Two passes because the inbox is a full snapshot of builds routed here.
    # Pass 1: collect routed remote ids (federated issue posts handled inline).
    routed: dict[str, tuple[dict, dict]] = {}
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
        if rid:
            routed[str(rid)] = (item, build)
    # AUT-910: admin-removed federated copies must not resurrect. The hub keeps
    # routing the removed build's post event, so the next sync would re-add the
    # copy; a tombstone blocks that. A tombstone whose build is no longer
    # routed is safe to prune, keeping the table bounded. Skip pruning when the
    # snapshot is empty so a transient hub gap cannot wipe every tombstone.
    tombstoned: set[str] = set(await db.scalars(select(SocialRemoteTombstone.remote_build_id)))
    if routed:
        for rid in tombstoned - routed.keys():
            await db.delete(await db.get(SocialRemoteTombstone, rid))
    existing: set[str] = set(await db.scalars(
        select(SocialBuild.remote_build_id).where(
            SocialBuild.remote_build_id.in_(routed.keys())
        )
    ))
    for rid, (item, build) in routed.items():
        if rid in tombstoned or rid in existing:
            continue
        db.add(SocialBuild(
            author_display_name=build.get("author_display_name", "Unknown"),
            remote_author_display_name=build.get("author_display_name"),
            server_name=build.get("server_name"),
            title=build.get("title", "Untitled build"),
            caption=build.get("caption"),
            origin="remote",
            remote_build_id=rid,
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
    """Apply a federated comment/like/remove event to the matching local copy."""
    if not isinstance(event, dict):
        return
    if event.get("event_type") == "remove":
        # Takedown (AUT-902): delete the local copy of a post the origin (or
        # hub operator) removed. Issue blog posts are routed to their handler.
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            return
        build_id = payload.get("build_id")
        if not build_id:
            return
        if payload.get("post_type") == "issue":
            from app.api.v1.issues import apply_issue_event

            await apply_issue_event(db, event)
            return
        build = await db.get(SocialBuild, str(build_id))
        if not build:
            build = await db.scalar(
                select(SocialBuild).where(SocialBuild.remote_build_id == str(build_id))
            )
        if not build or build.status != "published":
            return
        # Defense-in-depth (AUT-907): only purge federated copies. A locally
        # hosted build is removed only through its own server's delete/sharing
        # actions (which call the hub's origin-verified /v1/remove) — a hub
        # relayed `remove` must never be able to take down a peer's local post.
        if build.origin == "local":
            return
        await _purge_build(db, build)
        await db.flush()
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