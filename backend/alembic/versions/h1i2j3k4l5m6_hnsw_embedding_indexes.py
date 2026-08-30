"""Convert embedding indexes to HNSW (pgvector >= 0.5).

The original pgvector migration (g7h8i9j0k1l2) built IVFFlat indexes, which
need training data and lists tuned to row count; on small per-user tables a
seq scan or HNSW is better. This migration is idempotent: on databases that
already applied the IVFFlat version it drops those indexes and rebuilds them
as HNSW; on fresh databases (where g7h8i9j0k1l2 already creates HNSW) the
drop is a no-op and the index is simply rebuilt.
"""

import sqlalchemy as sa
from alembic import op

from app.core.config import settings  # noqa: E402

revision = "h1i2j3k4l5m6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_TABLES = ("diagnostics", "service_records", "modifications", "receipts")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_embedding")
        op.execute(
            f"CREATE INDEX idx_{table}_embedding ON {table} "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    # Rebuild as IVFFlat, matching the original migration's shape.
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_embedding")
        op.execute(
            f"CREATE INDEX idx_{table}_embedding ON {table} "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
