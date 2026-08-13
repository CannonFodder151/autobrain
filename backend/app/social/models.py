"""Social + federation-hub models (AUT-294 rev 7, AUT-332)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.session import Base


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
    """A build photo (webp in MinIO). build_id is null for pre-post uploads."""

    __tablename__ = "social_photos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    build_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("social_builds.id"), index=True)
    uploader_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    file_key: Mapped[str] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
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
