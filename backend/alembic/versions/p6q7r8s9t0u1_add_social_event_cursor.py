"""add_social_event_cursor

Community Garage (AUT-462): track the federated like/comment event cursor so
event pulls resume where they left off instead of re-applying (FD-1).

Revision ID: p6q7r8s9t0u1
Revises: n4p5q6r7s8t9
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "n4p5q6r7s8t9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("social_server_config", sa.Column("last_event_sync", sa.Integer(), nullable=True))
    # Federated comments/likes carry no local user id (FD-1 remote events).
    op.alter_column("social_likes", "author_user_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("social_comments", "author_user_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    op.alter_column("social_comments", "author_user_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("social_likes", "author_user_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("social_server_config", "last_event_sync")
