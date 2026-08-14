"""add_social_issue_photos

Community Garage Issues Blog (AUT-709): let issue posts carry up to 4 photos.
Reuses the existing social_photos table + MinIO upload pipeline by adding a
nullable issue_id link (mirror of the build_id link), so no new media storage
or upload endpoint is needed.

AUT-510 pattern: DDL ops are guarded so DBs where the column was created by
bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "m3rge02"
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
    if not _has_column("social_photos", "issue_id"):
        op.add_column(
            "social_photos",
            sa.Column("issue_id", sa.String(36), sa.ForeignKey("social_issue_posts.id"), nullable=True),
        )
    if not _has_index("ix_social_photos_issue_id", "social_photos"):
        op.create_index("ix_social_photos_issue_id", "social_photos", ["issue_id"])


def downgrade() -> None:
    if _has_index("ix_social_photos_issue_id", "social_photos"):
        op.drop_index("ix_social_photos_issue_id", table_name="social_photos")
    if _has_column("social_photos", "issue_id"):
        op.drop_column("social_photos", "issue_id")
