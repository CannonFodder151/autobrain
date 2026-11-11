"""merge aut423 heads

Merges the public developer API (api_keys + webhooks) branch with main.
"""
from typing import Sequence, Union

from alembic import context, op

revision: str = "m3rge09"
down_revision: Union[str, Sequence[str], None] = ["m3rge08", "aut423_add_api_keys_and_webhooks"]
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