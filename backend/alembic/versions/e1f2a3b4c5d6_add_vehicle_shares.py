"""add_vehicle_shares

Revision ID: e1f2a3b4c5d6
Revises: g7h8i9j0k1l2
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_shares",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "vehicle_id",
            sa.String(36),
            sa.ForeignKey("vehicles.id"),
            nullable=False,
        ),
        sa.Column(
            "invitee_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("vehicle_id", "invitee_user_id", name="uq_vehicle_share"),
    )
    op.create_index("ix_vehicle_shares_vehicle_id", "vehicle_shares", ["vehicle_id"])
    op.create_index(
        "ix_vehicle_shares_invitee_user_id", "vehicle_shares", ["invitee_user_id"]
    )


def downgrade() -> None:
    op.drop_table("vehicle_shares")
