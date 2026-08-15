"""Social + federation-hub models (AUT-294 rev 7, AUT-332)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base
from app.db.types import StringArray


def _uuid() -> str:
    return str(uuid.uuid4())


class SocialBuild(Base):
    """A shared build post. Local builds reference the origin vehicle and get a
    live snapshot; remote/demo builds carry their own stored snapshot JSON."""

    __tablename__ = "social_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    author_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    # Identity at share time, so the feed never needs a join to users.
    author_display_name: Mapped[str] = mapped_column(String(120))
    # "<Display name> from <Server Name>" — server part is null for local-only.
    server_name: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    caption: Mapped[str | None] = mapped_column(Text)
    # local | remote | demo
    origin: Mapped[str] = mapped_column(String(10), default="local", index=True)
    # Hub identity for remote builds (never re-federated back out).
    remote_build_id: Mapped[str | None] = mapped_column(String(64), index=True)
    remote_server_id: Mapped[str | None] = mapped_column(String(64))
    remote_author_display_name: Mapped[str | None] = mapped_column(String(120))
    # Deterministic snapshot built at share time (no AI). Live for local builds.
    snapshot_json: Mapped[str | None] = mapped_column(Text)
    # Specs/mods/odometer/notes may be redacted per share scope on display.
    status: Mapped[str] = mapped_column(String(20), default="published")  # published/hidden
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SocialPhoto(Base):
    """A social photo (webp in MinIO). build_id/issue_id/comment_id are null
    for pre-post uploads; exactly one is set once attached to a build, an issue
    post, or an issue comment (AUT-736, 1 photo per reply)."""

    __tablename__ = "social_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    build_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("social_builds.id"), index=True)
    issue_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("social_issue_posts.id"), index=True)
    comment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("social_issue_comments.id", ondelete="CASCADE"), index=True
    )
    uploader_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    file_key: Mapped[str] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    # Display order within the build (AUT-675 reorder).
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialComment(Base):
    __tablename__ = "social_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    build_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_builds.id"), index=True)
    # Null for comments applied from federated events (no local user).
    author_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    author_display_name: Mapped[str] = mapped_column(String(120))
    server_name: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialLike(Base):
    __tablename__ = "social_likes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    build_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_builds.id"), index=True)
    # Null for likes applied from federated events (no local user).
    author_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    author_display_name: Mapped[str] = mapped_column(String(120))
    server_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("build_id", "author_user_id", name="uq_social_like"),)


class SocialShareScope(Base):
    """Per-build opt-in share scope (req 11). Default minimal: photos + specs + mods."""

    __tablename__ = "social_share_scopes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    build_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_builds.id"), unique=True)
    allow_photos: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_specs: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_mods: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_odometer: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_notes: Mapped[bool] = mapped_column(Boolean, default=False)


class SocialIssuePost(Base):
    """A blog-style help request (AUT-627). Community-visible: every premium
    user across the federation can read/answer, regardless of vehicle ownership.
    No AI in the authoring path — tags are deterministic, bodies are plaintext."""

    __tablename__ = "social_issue_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    author_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    author_display_name: Mapped[str] = mapped_column(String(120))
    server_name: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text)
    # Deterministic snapshot of the author's vehicle at post time (make/model/year).
    vehicle_snapshot_json: Mapped[str | None] = mapped_column(Text)
    # Fixed-vocabulary tags (deterministic match — never AI).
    tags: Mapped[list[str]] = mapped_column(StringArray(), default=list)
    # open | answered | resolved
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    resolved_comment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    # local | remote | demo
    origin: Mapped[str] = mapped_column(String(10), default="local", index=True)
    remote_post_id: Mapped[str | None] = mapped_column(String(64), index=True)
    remote_server_id: Mapped[str | None] = mapped_column(String(64))
    # Remote copies carry the origin's signed photo URLs (AUT-756); local posts
    # keep using the social_photos table + MinIO presigns instead.
    photo_urls_json: Mapped[str | None] = mapped_column(Text)
    # Admin moderation flag: hidden posts are excluded from browse + search.
    status_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Client-side microsecond-faithful default so keyset cursors compare exactly
    # on every dialect (sqlite's func.now() is second-precision text).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SocialIssueComment(Base):
    """A help comment on an issue post. is_answer pins the resolved answer."""

    __tablename__ = "social_issue_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_issue_posts.id"), index=True)
    # Null for comments applied from federated events (no local user).
    author_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    author_display_name: Mapped[str] = mapped_column(String(120))
    server_name: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    # Origin comment id for remote copies, so answer events can be matched
    # exactly instead of by body (AUT-756).
    remote_comment_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialIssueFlag(Base):
    """A user report on an issue post OR comment (moderation queue, AUT-832).

    Post flags leave comment_id NULL; comment flags carry both the post anchor
    (context) and the comment id. Dedupe is per-target: one report per user per
    post, and one per user per comment (partial unique indexes below).
    """

    __tablename__ = "social_issue_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(String(36), ForeignKey("social_issue_posts.id"), index=True)
    comment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("social_issue_comments.id", ondelete="CASCADE"), index=True
    )
    flagged_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_social_issue_flag_post",
            "post_id",
            "flagged_by_user_id",
            unique=True,
            postgresql_where=text("comment_id IS NULL"),
            sqlite_where=text("comment_id IS NULL"),
        ),
        Index(
            "uq_social_issue_flag_comment",
            "comment_id",
            "flagged_by_user_id",
            unique=True,
            postgresql_where=text("comment_id IS NOT NULL"),
            sqlite_where=text("comment_id IS NOT NULL"),
        ),
    )


class SocialServerConfig(Base):
    """Singleton row holding the admin toggles + hub registration state.

    Defaults come from env settings on first creation; the admin API overrides
    them at runtime (survives restarts).
    """

    __tablename__ = "social_server_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    feature_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    federation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    server_name: Mapped[str | None] = mapped_column(String(120))
    server_email: Mapped[str | None] = mapped_column(String(255))
    server_hub_url: Mapped[str | None] = mapped_column(String(255))  # fallback: settings
    hub_status: Mapped[str] = mapped_column(String(20), default="unregistered")  # unregistered/registered/error
    hub_server_id: Mapped[str | None] = mapped_column(String(64))
    hub_api_key: Mapped[str | None] = mapped_column(String(128))
    hub_private_key: Mapped[str | None] = mapped_column(String(128))  # ed25519, hub auth
    last_inbox_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_sync: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


async def get_server_config(db: AsyncSession) -> SocialServerConfig:
    """Return the singleton config row, creating it from env defaults if absent."""
    cfg = await db.get(SocialServerConfig, 1)
    if cfg is not None:
        return cfg
    cfg = SocialServerConfig(
        id=1,
        feature_enabled=settings.SOCIAL_FEATURE_ENABLED,
        federation_enabled=settings.SOCIAL_FEDERATION_ENABLED,
    )
    db.add(cfg)
    await db.flush()
    return cfg
