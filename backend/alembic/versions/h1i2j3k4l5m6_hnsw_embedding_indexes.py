"""Convert embedding indexes to HNSW (pgvector >= 0.5).

The original pgvector migration (g7h8i9j0k1l2) built HNSW indexes directly,
which need no training data or list tuning. This migration is idempotent: on
databases that already applied g7h8i9j0k1l2 the drop is a no-op and the index
is simply rebuilt as HNSW; on databases that previously had IVFFlat indexes
it drops those and rebuilds them as HNSW.
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
