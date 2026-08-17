"""add_remote_tombstones

AUT-910: social_remote_tombstones records remote_build_ids of federated
copies an admin removed, so the next federation inbox sync does not re-add
them. Pruned by _sync_federation once the hub stops routing the build.

AUT-510 pattern: DDL ops are guarded so DBs where the table was created by
bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, None] = "v1w2x3y4z5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _online() -> bool:
    return not context.is_offline_mode()

def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()

def upgrade() -> None:
    if not _has_table("social_remote_tombstones"):
        op.create_table(
            "social_remote_tombstones",
            sa.Column("remote_build_id", sa.String(64), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

def downgrade() -> None:
    if not _has_table("social_remote_tombstones"):
        return
    op.drop_table("social_remote_tombstones")