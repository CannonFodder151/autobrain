"""Alembic migration: add pgvector embedding columns to remaining entity tables."""

import sqlalchemy as sa
from alembic import op

from app.core.config import settings  # noqa: E402

revision = "g7h8i9j0k1l3"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None

_DIM = settings.EMBEDDING_DIMENSION


def _column_is_text(conn, table: str) -> bool:
    """Check if embedding column exists and is TEXT type (create_all fallback)."""
    row = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = 'embedding'"
        ),
        {"t": table},
    ).fetchone()
    return row is not None and row[0].lower() == "text"


def upgrade() -> None:
    # Install pgvector extension if not already present (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    conn = op.get_bind()
    for table in ("fuel_price_snapshots", "devices", "market_listing_cache", "vehicles"):
        # The table may not exist yet if an earlier revision (e.g. aut3448 for
        # fuel_price_snapshots) hasn't run on this branch. Skip rather than
        # raising UndefinedTableError on parallel alembic branches.
        if not sa.inspect(conn).has_table(table):
            continue
        # The create_all fallback on hosted creates embedding as Text; convert
        # it to vector so the HNSW index below accepts it.
        if _column_is_text(conn, table):
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS embedding vector({_DIM})")

    # HNSW index (pgvector >= 0.5): no training data or tuning required, and on
    # small per-user tables it beats IVFFlat — which needs lists tuned to row
    # count and a training probe pass. Cosine ops matches search's `a <=> b`.
    for table in ("fuel_price_snapshots", "devices", "market_listing_cache", "vehicles"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_embedding ON {table} "
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