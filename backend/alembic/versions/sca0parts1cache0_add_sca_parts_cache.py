"""add_sca_parts_cache

AUT-1792: Supercheap Auto parts-guide cache table. Keyed by resolved
vehicle identity (make|model|year) so repeated SCA lookups are stable and
cheap (24h TTL in app/services/parts_guide.py).

Guarded so DBs created by the bootstrap create_all fallback apply cleanly
as a no-op.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "sca0parts1cache0"
down_revision: Union[str, None] = "o5n6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_index(name: str, table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_table("sca_parts_cache"):
        op.create_table(
            "sca_parts_cache",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("cache_key", sa.String(255), nullable=False),
            sa.Column("parts_json", sa.Text(), nullable=False),
            sa.Column("category_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if _online() and not _has_index("uq_sca_cache_key", "sca_parts_cache"):
        op.create_unique_constraint("uq_sca_cache_key", "sca_parts_cache", ["cache_key"])
    if _online() and not _has_index("ix_sca_cache_key", "sca_parts_cache"):
        op.create_index("ix_sca_cache_key", "sca_parts_cache", ["cache_key"])


def downgrade() -> None:
    if _has_table("sca_parts_cache"):
        op.drop_table("sca_parts_cache")
