"""AUT-3469: Fix pgvector native type binding in search.

- Replace string-literal vector casting with native pgvector SQLAlchemy binding
- Add partial index WHERE embedding IS NULL for efficient backfill queries
- Add embedding_updated_at column to track when embeddings were last updated
"""

import sqlalchemy as sa
from alembic import op
from app.core.config import settings

revision = "aut3469_pgvector_native_binding"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None

_DIM = settings.EMBEDDING_DIMENSION

_TABLES = (
    "diagnostics",
    "service_records",
    "modifications",
    "receipts",
    "social_issue_posts",
)


def upgrade() -> None:
    # Add embedding_updated_at column to all tables with embeddings
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ"
        )

    # Create partial indexes for rows where embedding IS NULL
    # These help efficiently find rows that need embedding backfill
    for table in _TABLES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_embedding_null "
            f"ON {table} (id) WHERE embedding IS NULL"
        )


def downgrade() -> None:
    # Drop partial indexes
    for table in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_embedding_null")

    # Drop embedding_updated_at columns
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding_updated_at")
