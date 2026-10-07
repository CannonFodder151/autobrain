"""Alembic migration: add pgvector embedding columns to remaining entity tables."""

import sqlalchemy as sa
from alembic import op

from app.core.config import settings  # noqa: E402

revision = "g7h8i9j0k1l3"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None

_DIM = settings.EMBEDDING_DIMENSION


def upgrade() -> None:
    # Install pgvector extension if not already present (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding columns (dimension from config, matches the embedding model).
    for table in ("fuel_price_snapshots", "devices", "market_listing_cache", "vehicles"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector({_DIM})")

    # HNSW index (pgvector >= 0.5): no training data or tuning required, and on
    # small per-user tables it beats IVFFlat — which needs lists tuned to row
    # count and a training probe pass. Cosine ops matches search's `a <=> b`.
    for table in ("fuel_price_snapshots", "devices", "market_listing_cache", "vehicles"):
        op.execute(
            f"CREATE INDEX idx_{table}_embedding ON {table} "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vehicles_embedding")
    op.execute("DROP INDEX IF EXISTS idx_market_listing_cache_embedding")
    op.execute("DROP INDEX IF EXISTS idx_devices_embedding")
    op.execute("DROP INDEX IF EXISTS idx_fuel_price_snapshots_embedding")
    op.execute("ALTER TABLE vehicles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE market_listing_cache DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE fuel_price_snapshots DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")