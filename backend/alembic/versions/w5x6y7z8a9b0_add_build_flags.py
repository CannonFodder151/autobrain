"""add_build_flags

AUT-883 moderation queue for builds: social_build_flags table reports a build
post OR build comment (comment_id null = post report), with per-target dedupe
partial unique indexes mirroring social_issue_flags.

AUT-510 pattern: DDL ops are guarded so DBs where the table was created by
bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "w5x6y7z8a9b0"
down_revision: Union[str, None] = "v1w2x3y4z5a6"
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
    if not _has_table("social_build_flags"):
        op.create_table(
            "social_build_flags",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=False),
            sa.Column("comment_id", sa.String(36), sa.ForeignKey("social_comments.id", ondelete="CASCADE"), nullable=True),
            sa.Column("flagged_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.String(200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_social_build_flags_build_id", "social_build_flags", ["build_id"])
        op.create_index("ix_social_build_flags_comment_id", "social_build_flags", ["comment_id"])
        op.create_index(
            "uq_social_build_flag_post",
            "social_build_flags",
            ["build_id", "flagged_by_user_id"],
            unique=True,
            postgresql_where=sa.text("comment_id IS NULL"),
            sqlite_where=sa.text("comment_id IS NULL"),
        )
        op.create_index(
            "uq_social_build_flag_comment",
            "social_build_flags",
            ["comment_id", "flagged_by_user_id"],
            unique=True,
            postgresql_where=sa.text("comment_id IS NOT NULL"),
            sqlite_where=sa.text("comment_id IS NOT NULL"),
        )


def downgrade() -> None:
    if not _has_table("social_build_flags"):
        return
    for name in ("uq_social_build_flag_comment", "uq_social_build_flag_post",
                 "ix_social_build_flags_comment_id", "ix_social_build_flags_build_id"):
        if _has_index(name, "social_build_flags"):
            op.drop_index(name, table_name="social_build_flags")
    op.drop_table("social_build_flags")
