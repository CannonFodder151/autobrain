"""add_social_photo_position

Community Garage (AUT-675): photo display order on builds, so the edit flow can
reorder/upload/remove photos. Existing photos keep creation-time order
(position defaults to 0, tie-broken by created_at).

Revision ID: q1r2s3t4u5v6
Revises: q7r8s9t0u1v2
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "q7r8s9t0u1v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("social_photos", "position"):
        op.add_column(
            "social_photos",
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("social_photos", "position"):
        op.drop_column("social_photos", "position")
