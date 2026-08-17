"""merge build-flags and dongle-devices branches

The add_build_flags chain (v1w2x3y4z5a6 -> w5x6y7z8a9b0, AUT-883) and the
remote-tombstones -> dongle-devices chain (v1w2x3y4z5a6 -> x1y2z3a4b5c6 ->
d1e2f3a4b5c6, AUT-910/AUT-918) fork at v1w2x3y4z5a6, leaving two alembic heads
and breaking `alembic upgrade head` in the boot command. d1e2f3a4b5c6 also
fixed a duplicate revision id (a1b2c3d4e5f6 was already claimed by
add_user_max_vehicles, so alembic refused to load the script tree at all;
fresh installs failed and bootstrap fell back to create_all). This merge
re-unifies both branches so each applies cleanly on DBs stamped at either
head predecessor. No schema change.

AUT-510 pattern: no-op upgrade body.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'm3rge03'
down_revision: Union[str, Sequence[str], None] = ('w5x6y7z8a9b0', 'd1e2f3a4b5c6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass