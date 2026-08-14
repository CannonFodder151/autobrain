"""add_issue_blog_tables

Community Garage Issues Blog (AUT-627): social_issue_posts / comments / flags
plus the pgvector embedding column on posts for hybrid search.

Revision ID: u1v2w3x4y5z6
Revises: p6q7r8s9t0u1
Create Date: 2026-08-14 00:00:00.000000

AUT-510 pattern: every DDL op is guarded so DBs where the tables were created
by bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

from app.core.config import settings

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DIM = settings.EMBEDDING_DIMENSION


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


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_table("social_issue_posts"):
        op.create_table(
            "social_issue_posts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("author_display_name", sa.String(120), nullable=False),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("title", sa.String(150), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("vehicle_snapshot_json", sa.Text(), nullable=True),
            sa.Column("tags", sa.ARRAY(sa.String(32)), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("resolved_comment_id", sa.String(36), nullable=True),
            sa.Column("origin", sa.String(10), nullable=False, server_default="local"),
            sa.Column("remote_post_id", sa.String(64), nullable=True),
            sa.Column("remote_server_id", sa.String(64), nullable=True),
            sa.Column("status_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    for idx, cols in {
        "ix_social_issue_posts_author_user_id": ["author_user_id"],
        "ix_social_issue_posts_status": ["status"],
        "ix_social_issue_posts_origin": ["origin"],
        "ix_social_issue_posts_status_hidden": ["status_hidden"],
        "ix_social_issue_posts_resolved_comment_id": ["resolved_comment_id"],
        "ix_social_issue_posts_created_at": ["created_at"],
    }.items():
        if not _has_index(idx, "social_issue_posts"):
            op.create_index(idx, "social_issue_posts", cols)
    if not _has_index("ix_social_issue_posts_remote_post_id", "social_issue_posts"):
        op.create_index("ix_social_issue_posts_remote_post_id", "social_issue_posts", ["remote_post_id"], unique=True)

    if not _has_table("social_issue_comments"):
        op.create_table(
            "social_issue_comments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("post_id", sa.String(36), sa.ForeignKey("social_issue_posts.id"), nullable=False),
            sa.Column("author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("author_display_name", sa.String(120), nullable=False),
            sa.Column("server_name", sa.String(120), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_answer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if not _has_index("ix_social_issue_comments_post_id", "social_issue_comments"):
        op.create_index("ix_social_issue_comments_post_id", "social_issue_comments", ["post_id"])

    if not _has_table("social_issue_flags"):
        op.create_table(
            "social_issue_flags",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("post_id", sa.String(36), sa.ForeignKey("social_issue_posts.id"), nullable=False),
            sa.Column("flagged_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("post_id", "flagged_by_user_id", name="uq_social_issue_flag"),
        )
    if not _has_index("ix_social_issue_flags_post_id", "social_issue_flags"):
        op.create_index("ix_social_issue_flags_post_id", "social_issue_flags", ["post_id"])

    # pgvector embedding for hybrid search (title + body + tags).
    if _has_table("social_issue_posts") and not _has_column("social_issue_posts", "embedding"):
        op.execute(f"ALTER TABLE social_issue_posts ADD COLUMN embedding vector({_DIM})")
    if not _has_index("idx_social_issue_posts_embedding", "social_issue_posts"):
        op.execute(
            "CREATE INDEX idx_social_issue_posts_embedding ON social_issue_posts "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_social_issue_posts_embedding")
    op.drop_table("social_issue_flags")
    op.drop_table("social_issue_comments")
    op.drop_table("social_issue_posts")
