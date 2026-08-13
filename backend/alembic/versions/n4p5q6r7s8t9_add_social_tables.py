"""add_social_tables

Community Garage (AUT-332): social build/photo/comment/like/share-scope tables
plus the singleton server config holding the admin toggles.

Revision ID: n4p5q6r7s8t9
Revises: a5b6c7d8e9f0
Create Date: 2026-08-12 00:00:00.000000

AUT-510: reparented onto a5b6c7d8e9f0 (logbook gps_samples head) so the chain
is linear — previously this revised m3rge01 while the logbook branch also did,
forking the graph into two heads and making `alembic upgrade head` fail with
"Multiple head revisions" on both fresh and create_all-hybrid DBs. Every
DDL op is also guarded so already-present tables/indexes (created earlier by
bootstrap's create_all fallback) are skipped.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "n4p5q6r7s8t9"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_index(name: str, table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_table("social_server_config"):
        op.create_table(
            "social_server_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("feature_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("federation_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("server_email", sa.String(255), nullable=True),
            sa.Column("server_hub_url", sa.String(255), nullable=True),
            sa.Column("hub_status", sa.String(20), nullable=False, server_default="unregistered"),
            sa.Column("hub_server_id", sa.String(64), nullable=True),
            sa.Column("hub_api_key", sa.String(128), nullable=True),
            sa.Column("hub_private_key", sa.String(128), nullable=True),
            sa.Column("last_inbox_sync", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_table("social_builds"):
        op.create_table(
            "social_builds",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("author_display_name", sa.String(120), nullable=False),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("origin", sa.String(10), nullable=False, server_default="local"),
            sa.Column("remote_build_id", sa.String(64), nullable=True),
            sa.Column("remote_server_id", sa.String(64), nullable=True),
            sa.Column("remote_author_display_name", sa.String(120), nullable=True),
            sa.Column("snapshot_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="published"),
            sa.Column("share_token", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_index("ix_social_builds_vehicle_id", "social_builds"):
        op.create_index("ix_social_builds_vehicle_id", "social_builds", ["vehicle_id"])
    if not _has_index("ix_social_builds_author_user_id", "social_builds"):
        op.create_index("ix_social_builds_author_user_id", "social_builds", ["author_user_id"])
    if not _has_index("ix_social_builds_origin", "social_builds"):
        op.create_index("ix_social_builds_origin", "social_builds", ["origin"])
    if not _has_index("ix_social_builds_remote_build_id", "social_builds"):
        op.create_index("ix_social_builds_remote_build_id", "social_builds", ["remote_build_id"])
    if not _has_index("ix_social_builds_share_token", "social_builds"):
        op.create_index("ix_social_builds_share_token", "social_builds", ["share_token"], unique=True)

    if not _has_table("social_photos"):
        op.create_table(
            "social_photos",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=True),
            sa.Column("uploader_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("file_key", sa.String(255), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_index("ix_social_photos_build_id", "social_photos"):
        op.create_index("ix_social_photos_build_id", "social_photos", ["build_id"])

    if not _has_table("social_comments"):
        op.create_table(
            "social_comments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=False),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("author_display_name", sa.String(120), nullable=False),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_index("ix_social_comments_build_id", "social_comments"):
        op.create_index("ix_social_comments_build_id", "social_comments", ["build_id"])

    if not _has_table("social_likes"):
        op.create_table(
            "social_likes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=False),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("author_display_name", sa.String(120), nullable=False),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("build_id", "author_user_id", name="uq_social_like"),
        )
    if not _has_index("ix_social_likes_build_id", "social_likes"):
        op.create_index("ix_social_likes_build_id", "social_likes", ["build_id"])

    if not _has_table("social_share_scopes"):
        op.create_table(
            "social_share_scopes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=False),
            sa.Column("allow_photos", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_specs", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_mods", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_odometer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_notes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.UniqueConstraint("build_id", name="uq_social_share_scope_build"),
        )


def downgrade() -> None:
    op.drop_table("social_share_scopes")
    op.drop_table("social_likes")
    op.drop_table("social_comments")
    op.drop_table("social_photos")
    op.drop_table("social_builds")
    op.drop_table("social_server_config")
