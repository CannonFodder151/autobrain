"""Social federation sync helpers."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.social import federation
from app.social.federation import FederationUnavailable
from app.social.models import (
    SocialBuild,
    SocialComment,
    SocialLike,
    SocialRemoteTombstone,
    get_server_config,
)
from app.social.snapshot import dumps

logger = get_logger(__name__)

_INBOX_SYNC_TTL_SECONDS = 60


async def _sync_federation(db: AsyncSession) -> None:
    cfg = await get_server_config(db)
    if not cfg.federation_enabled or cfg.hub_status not in ("registered", "pending") or not cfg.hub_server_id:
        return
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
        if last_sync.tzinfo is None:
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
    routed: dict[str, tuple[dict, dict]] = {}
    for item in remote_builds:
        if not isinstance(item, dict):
            continue
        build = item.get("build") or item
        if not isinstance(build, dict):
            continue
        if build.get("type") == "issue":
            from app.api.v1.issues_pkg.federation import pull_remote_issue
            await pull_remote_issue(db, item, build)
            continue
        rid = build.get("remote_build_id") or build.get("build_id")
        if rid:
            routed[str(rid)] = (item, build)
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
    if not isinstance(event, dict):
        return
    if event.get("event_type") == "remove":
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            return
        build_id = payload.get("build_id")
        if not build_id:
            return
        if payload.get("post_type") == "issue":
            from app.api.v1.issues_pkg.federation import apply_issue_event
            await apply_issue_event(db, event)
            return
        build = await db.get(SocialBuild, str(build_id))
        if not build:
            build = await db.scalar(
                select(SocialBuild).where(SocialBuild.remote_build_id == str(build_id))
            )
        if not build or build.status != "published":
            return
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
        from app.api.v1.issues_pkg.federation import apply_issue_event
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


async def _purge_build(db: AsyncSession, build: SocialBuild) -> None:
    from sqlalchemy import delete, update
    from app.social.models import SocialPhoto, SocialShareScope
    await db.execute(
        update(SocialPhoto)
        .where(SocialPhoto.build_id == build.id)
        .values(build_id=None)
    )
    await db.execute(delete(SocialComment).where(SocialComment.build_id == build.id))
    await db.execute(delete(SocialLike).where(SocialLike.build_id == build.id))
    await db.execute(delete(SocialShareScope).where(SocialShareScope.build_id == build.id))
    await db.delete(build)


async def _push_event_safe(db: AsyncSession, build: SocialBuild, kind: str, payload: dict) -> None:
    cfg = await get_server_config(db)
    origin_build_id = build.remote_build_id if build.origin == "remote" else build.id
    try:
        await federation.push_event(cfg, origin_build_id, kind, payload)
    except (FederationUnavailable, Exception) as exc:
        logger.warning("social_event_push_failed", kind=kind, build_id=build.id, error=str(exc))