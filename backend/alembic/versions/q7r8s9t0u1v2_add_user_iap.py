"""add store-native IAP fields to users

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: str | None = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("iap_platform", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("iap_product_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("iap_transaction_id", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("iap_original_transaction_id", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("iap_purchase_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("iap_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("iap_status", sa.String(length=16), nullable=True))
    op.create_index("ix_users_iap_platform", "users", ["iap_platform"])
    op.create_index("ix_users_iap_transaction_id", "users", ["iap_transaction_id"])
    op.create_index("ix_users_iap_original_transaction_id", "users", ["iap_original_transaction_id"])

def downgrade() -> None:
    op.drop_index("ix_users_iap_original_transaction_id", table_name="users")
    op.drop_index("ix_users_iap_transaction_id", table_name="users")
    op.drop_index("ix_users_iap_platform", table_name="users")
    op.drop_column("users", "iap_status")
    op.drop_column("users", "iap_expires_at")
    op.drop_column("users", "iap_purchase_token")
    op.drop_column("users", "iap_original_transaction_id")
    op.drop_column("users", "iap_transaction_id")
    op.drop_column("users", "iap_product_id")
    op.drop_column("users", "iap_platform")
