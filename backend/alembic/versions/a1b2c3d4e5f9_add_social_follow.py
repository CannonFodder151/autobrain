"""add social follow model (AUT-139)

SocialFollow: a local user follows another user or a federated server.
Deduped per (follower, target) via two partial unique indexes. Remote copies
of follows are not stored locally — the timeline is filtered by the local
user's followed_user_id + followed_server_name set.

AUT-139: follow/unfollow endpoints, timeline filtering by followed users/
servers, and the frontend follow button.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "a1b2c3d4e5f9"
down_revision: Union[str, None] = "z2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def upgrade() -> None:
    if _has_table("social_follows"):
        return
    op.create_table(
        "social_follows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("follower_user_id", sa.String(length=36), nullable=False),
        sa.Column("followed_user_id", sa.String(length=36), nullable=True),
        sa.Column("followed_server_name", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["follower_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["followed_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "follower_user_id",
            "followed_user_id",
            name="uq_social_follow_user",
        ),
        sa.UniqueConstraint(
            "follower_user_id",
            "followed_server_name",
            name="uq_social_follow_server",
        ),
    )
    op.create_index(
        "ix_social_follows_follower_user_id",
        "social_follows",
        ["follower_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_social_follows_followed_user_id",
        "social_follows",
        ["followed_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_social_follows_followed_server_name",
        "social_follows",
        ["followed_server_name"],
        unique=False,
    )


def downgrade() -> None:
    if not _has_table("social_follows"):
        return
    op.drop_table("social_follows")