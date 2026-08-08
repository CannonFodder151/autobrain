"""Alembic migration: add pgvector extension and vector columns to searchable tables."""

import sqlalchemy as sa
from alembic import op

revision = "g7h8i9j0k1l2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Install pgvector extension (PostgreSQL must have vector extension available,
    # use pgvector/pgvector:pg16 Docker image).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding columns (1536-dim, matches text-embedding-3-small output size).
    op.execute(
        "ALTER TABLE diagnostics ADD COLUMN embedding vector(1536)"
    )
    op.execute(
        "ALTER TABLE service_records ADD COLUMN embedding vector(1536)"
    )
    op.execute(
        "ALTER TABLE modifications ADD COLUMN embedding vector(1536)"
    )
    op.execute(
        "ALTER TABLE receipts ADD COLUMN embedding vector(1536)"
    )

    # Create HNSW-style IVFFlat indexes for efficient similarity search.
    op.execute(
        "CREATE INDEX idx_diagnostics_embedding ON diagnostics "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_service_records_embedding ON service_records "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_modifications_embedding ON modifications "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_receipts_embedding ON receipts "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
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
