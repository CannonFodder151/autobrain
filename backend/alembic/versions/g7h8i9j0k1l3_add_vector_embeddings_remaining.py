"""add_vector_embeddings_remaining

Phase 1b (AUT-3512): extend pgvector embeddings to fuel_prices, devices,
market_listing_cache and vehicles tables so the full catalogue of
searchable entities gets HNSW-backed semantic search.  The original
embedding migration (g7h8i9j0k1l2) only covered diagnostics, service_records,
modifications and receipts; u1v2w3x4y5z6 added social_issue_posts.

Each DDL op is guarded so DBs where the column/index already exists apply
cleanly as a no-op (same idempotency pattern as u1v2w3x4y5z6).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

from app.core.config import settings  # noqa: E402

revision: str = "g7h8i9j0k1l3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DIM = settings.EMBEDDING_DIMENSION

_TABLES = ("fuel_prices", "devices", "market_listing_cache", "vehicles")


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {col["name"] for col in insp.get_columns(table)}


def _has_index(name: str, table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for table in _TABLES:
        if not _has_column(table, "embedding"):
            op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector({_DIM})")
        idx = f"idx_{table}_embedding"
        if not _has_index(idx, table):
            op.execute(
                f"CREATE INDEX {idx} ON {table} "
                "USING hnsw (embedding vector_cosine_ops)"
            )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_embedding")
        if _online():
            insp = sa.inspect(op.get_bind())
            cols = {col["name"] for col in insp.get_columns(table)}
            if "embedding" in cols:
                op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
        else:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
