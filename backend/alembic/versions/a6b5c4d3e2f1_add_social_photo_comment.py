"""add_social_photo_comment

Issues Blog (AUT-736): replies can carry one photo each, so SocialPhoto gets a
nullable comment_id link (exactly one of build_id/issue_id/comment_id).

AUT-510 pattern: guarded so DBs where the column already exists apply cleanly.

Chains onto a1b2c3d4e5f7 (AUT-709 issue-photo link, current head) so the graph
keeps a single head; the earlier merge m3rge02 is already a parent of that head.

Revision ID: a6b5c4d3e2f1
Revises: a1b2c3d4e5f7
Create Date: 2026-08-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "a6b5c4d3e2f1"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
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
    if not _has_column("social_photos", "comment_id"):
        op.add_column(
            "social_photos",
            sa.Column("comment_id", sa.String(36), sa.ForeignKey("social_issue_comments.id"), nullable=True),
        )
    if not _has_index("ix_social_photos_comment_id", "social_photos"):
        op.create_index("ix_social_photos_comment_id", "social_photos", ["comment_id"])


def downgrade() -> None:
    if _has_index("ix_social_photos_comment_id", "social_photos"):
        op.drop_index("ix_social_photos_comment_id", table_name="social_photos")
    if _has_column("social_photos", "comment_id"):
        op.drop_column("social_photos", "comment_id")
