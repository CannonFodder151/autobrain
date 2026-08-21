"""add has_had_trial to users

Adds the one-time 7-day free-trial guard column (AUT-1195/1196).

Merges the three heads (m3rge01/02/03) so ``alembic upgrade head`` keeps a
single resolution path; this migration is the new sole head.

Revision ID: t1a2b3c4d5e6
Revises: m3rge01, m3rge02, m3rge03
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = ("m3rge01", "m3rge02", "m3rge03")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("has_had_trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "has_had_trial")