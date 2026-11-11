"""Merge aut466b_apns_token head with main.

Merges the APNS token migration (AUT-466b) with the main branch.
"""
from typing import Sequence, Union

from alembic import context, op

revision: str = "m3rge10"
down_revision: Union[str, Sequence[str], None] = ["m3rge09", "aut466b_apns_token"]
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def upgrade() -> None:
    # This is a merge migration - no schema changes, just combines heads
    if not _online():
        return
    pass


def downgrade() -> None:
    # Cannot cleanly downgrade a merge
    pass