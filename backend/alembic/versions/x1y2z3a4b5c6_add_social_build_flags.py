"""add_social_build_flags

AUT-896 moderation: social_build_flags — user reports on shared build posts.
Mirrors social_issue_flags. Reports fan out to the federation hub as `report`
events; this table is the reporting server's local record.

Revision ID: x1y2z3a4b5c6
Revises: v1w2x3y4z5a6
Create Date: 2026-08-16 00:00:00.000000

AUT-510 pattern: every DDL op is guarded so DBs where the tables were created
by bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, None] = "v1w2x3y4z5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_index(name: str, table: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if _has_table("social_build_flags"):
        return
    op.create_table(
        "social_build_flags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("build_id", sa.String(36), sa.ForeignKey("social_builds.id"), nullable=False),
        sa.Column("flagged_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_social_build_flags_build_id", "social_build_flags", ["build_id"])
    if not _has_index("uq_social_build_flag", "social_build_flags"):
        op.create_index(
            "uq_social_build_flag", "social_build_flags", ["build_id", "flagged_by_user_id"], unique=True
        )


def downgrade() -> None:
    if _has_table("social_build_flags"):
        op.drop_index("uq_social_build_flag", table_name="social_build_flags")
        op.drop_index("ix_social_build_flags_build_id", table_name="social_build_flags")
        op.drop_table("social_build_flags")
