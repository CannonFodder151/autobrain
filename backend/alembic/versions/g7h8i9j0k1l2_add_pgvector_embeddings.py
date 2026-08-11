"""Alembic migration: add pgvector extension and vector columns to searchable tables."""

import sqlalchemy as sa
from alembic import op

# Build the vector dimension from config so the schema can't drift from
# EMBEDDING_DIMENSION (env.py already imports app settings for the DB URL).
from app.core.config import settings  # noqa: E402

revision = "g7h8i9j0k1l2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

_DIM = settings.EMBEDDING_DIMENSION


def upgrade() -> None:
    # Install pgvector extension (PostgreSQL must have vector extension available,
    # use pgvector/pgvector:pg16 Docker image).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding columns (dimension from config, matches the embedding model).
    for table in ("diagnostics", "service_records", "modifications", "receipts"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector({_DIM})")

    # HNSW index (pgvector >= 0.5): no training data or tuning required, and on
    # small per-user tables it beats IVFFlat — which needs lists tuned to row
    # count and a training probe pass. Cosine ops matches search's `a <=> b`.
    for table in ("diagnostics", "service_records", "modifications", "receipts"):
        op.execute(
            f"CREATE INDEX idx_{table}_embedding ON {table} "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_receipts_embedding")
    op.execute("DROP INDEX IF EXISTS idx_modifications_embedding")
    op.execute("DROP INDEX IF EXISTS idx_service_records_embedding")
    op.execute("DROP INDEX IF EXISTS idx_diagnostics_embedding")
    op.execute("ALTER TABLE receipts DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE modifications DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE service_records DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE diagnostics DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
