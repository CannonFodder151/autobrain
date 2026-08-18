"""add_issue_federation_columns

Issues Blog federation (AUT-756): remote copies of issue posts need somewhere
to keep the origin's signed photo URLs, and remote comments need their origin
id so answer events can be matched exactly. Both are nullable, so existing
local-only rows are untouched.

AUT-510 pattern: DDL ops are guarded so DBs where the columns were created by
bootstrap's create_all fallback apply cleanly as no-ops.

Revision ID: a6b5c4d3e2f2
Revises: a6b5c4d3e2f1
Create Date: 2026-08-15 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "a6b5c4d3e2f2"
down_revision: Union[str, None] = "a6b5c4d3e2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {col["name"] for col in insp.get_columns(table)}


def _has_index(name: str, table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_column("social_issue_posts", "photo_urls_json"):
        op.add_column("social_issue_posts", sa.Column("photo_urls_json", sa.Text(), nullable=True))
    if not _has_column("social_issue_comments", "remote_comment_id"):
        op.add_column(
            "social_issue_comments",
            sa.Column("remote_comment_id", sa.String(64), nullable=True),
        )
    if not _has_index("ix_social_issue_comments_remote_comment_id", "social_issue_comments"):
        op.create_index(
            "ix_social_issue_comments_remote_comment_id",
            "social_issue_comments",
            ["remote_comment_id"],
        )


def downgrade() -> None:
    if _has_index("ix_social_issue_comments_remote_comment_id", "social_issue_comments"):
        op.drop_index("ix_social_issue_comments_remote_comment_id", table_name="social_issue_comments")
    if _has_column("social_issue_comments", "remote_comment_id"):
        op.drop_column("social_issue_comments", "remote_comment_id")
    if _has_column("social_issue_posts", "photo_urls_json"):
        op.drop_column("social_issue_posts", "photo_urls_json")
