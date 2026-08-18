"""add_comment_flags_social_ban

AUT-832 moderation hub: comment flags on social_issue_flags (comment_id +
per-target dedupe indexes) and the users.social_banned moderation flag.

Revision ID: v1w2x3y4z5a6
Revises: a6b5c4d3e2f2
Create Date: 2026-08-15 00:00:00.000000

AUT-510 pattern: every DDL op is guarded so DBs where the tables were created
by bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "v1w2x3y4z5a6"
down_revision: Union[str, None] = "a6b5c4d3e2f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


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
    if _has_table("users") and not _has_column("users", "social_banned"):
        op.add_column("users", sa.Column("social_banned", sa.Boolean(), nullable=False, server_default=sa.false()))
    if _has_table("social_issue_posts") and not _has_column("social_issue_posts", "hidden_by_ban"):
        op.add_column(
            "social_issue_posts",
            sa.Column("hidden_by_ban", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _has_table("social_issue_flags"):
        return
    if not _has_column("social_issue_flags", "comment_id"):
        op.add_column(
            "social_issue_flags",
            sa.Column("comment_id", sa.String(36), nullable=True),
        )
    insp = sa.inspect(op.get_bind())
    bind = op.get_bind()
    old = next((ix for ix in insp.get_indexes("social_issue_flags")
                if ix["name"] == "uq_social_issue_flag"), None)
    if old is None:
        old = next((ix for ix in insp.get_indexes("social_issue_flags")
                    if ix.get("unique") and set(ix["column_names"] or []) == {"post_id", "flagged_by_user_id"}), None)
    if old is not None:
        name = old["name"]
        if bind.dialect.name == "postgresql":
            try:
                op.drop_constraint(name, "social_issue_flags", type_="unique")
            except Exception:
                op.drop_index(name, table_name="social_issue_flags")
        else:
            op.drop_index(name, table_name="social_issue_flags")
    if not _has_index("uq_social_issue_flag_post", "social_issue_flags"):
        op.create_index(
            "uq_social_issue_flag_post",
            "social_issue_flags",
            ["post_id", "flagged_by_user_id"],
            unique=True,
            postgresql_where=sa.text("comment_id IS NULL"),
            sqlite_where=sa.text("comment_id IS NULL"),
        )
    if not _has_index("uq_social_issue_flag_comment", "social_issue_flags"):
        op.create_index(
            "uq_social_issue_flag_comment",
            "social_issue_flags",
            ["comment_id", "flagged_by_user_id"],
            unique=True,
            postgresql_where=sa.text("comment_id IS NOT NULL"),
            sqlite_where=sa.text("comment_id IS NOT NULL"),
        )
    if not _has_index("ix_social_issue_flags_comment_id", "social_issue_flags"):
        op.create_index("ix_social_issue_flags_comment_id", "social_issue_flags", ["comment_id"])


def downgrade() -> None:
    if _has_table("social_issue_posts") and _has_column("social_issue_posts", "hidden_by_ban"):
        op.drop_column("social_issue_posts", "hidden_by_ban")
    if _has_table("social_issue_flags"):
        for name in ("ix_social_issue_flags_comment_id", "uq_social_issue_flag_comment", "uq_social_issue_flag_post"):
            if _has_index(name, "social_issue_flags"):
                op.drop_index(name, table_name="social_issue_flags")
        if _has_column("social_issue_flags", "comment_id"):
            op.drop_column("social_issue_flags", "comment_id")
    if _has_table("users") and _has_column("users", "social_banned"):
        op.drop_column("users", "social_banned")
