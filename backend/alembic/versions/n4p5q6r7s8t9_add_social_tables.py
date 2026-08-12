"""add_social_tables

Community Garage (AUT-332): social build/photo/comment/like/share-scope tables
plus the singleton server config holding the admin toggles.

Revision ID: n4p5q6r7s8t9
Revises: m3rge01
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n4p5q6r7s8t9"
down_revision: Union[str, None] = "m3rge01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("last_inbox_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
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
    op.create_index("ix_social_builds_vehicle_id", "social_builds", ["vehicle_id"])
    op.create_index("ix_social_builds_author_user_id", "social_builds", ["author_user_id"])
    op.create_index("ix_social_builds_origin", "social_builds", ["origin"])
    op.create_index("ix_social_builds_remote_build_id", "social_builds", ["remote_build_id"])
    op.create_index("ix_social_builds_share_token", "social_builds", ["share_token"], unique=True)

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
    op.create_index("ix_social_photos_build_id", "social_photos", ["build_id"])

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
    op.create_index("ix_social_comments_build_id", "social_comments", ["build_id"])

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
    op.create_index("ix_social_likes_build_id", "social_likes", ["build_id"])

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
