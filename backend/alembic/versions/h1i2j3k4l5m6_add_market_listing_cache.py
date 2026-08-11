"""Add market_listing_cache — cached CarsGuide/CarSales market data for valuations."""

import sqlalchemy as sa
from alembic import op

revision = "h1i2j3k4l5m6"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_listing_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("make", sa.String(64), nullable=False, index=True),
        sa.Column("model", sa.String(64), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="fallback"),
        sa.Column("listings", sa.Text(), nullable=True),
        sa.Column("median_price", sa.Float(), nullable=True),
        sa.Column("low_price", sa.Float(), nullable=True),
        sa.Column("high_price", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("make", "model", "year", name="uq_market_make_model_year"),
    )


def downgrade() -> None:
    op.drop_table("market_listing_cache")
