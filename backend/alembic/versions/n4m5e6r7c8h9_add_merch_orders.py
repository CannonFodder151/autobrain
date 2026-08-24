"""add merch_orders table

Revision ID: n4m5e6r7c8h9
Revises: m3rge04
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

revision: str = "n4m5e6r7c8h9"
down_revision: str | None = "m3rge04"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "merch_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount_total", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("shipping_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("merch_orders")
