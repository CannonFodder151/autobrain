"""Merge aut5092_dev_veh_type + g7h8i9j0k1l3 heads (AUT-4259 follow-up)

The pgvector embedding chain (g7h8i9j0k1l2 → h1i2j3k4l5m6 → g7h8i9j0k1l3) and the
device vehicle_type repair chain (m3rge07 → f7e8d9c0b1a2 → aut4925 → aut3448 →
aut5092_dev_veh_type) were both merged straight into main, leaving two script-tree
heads. This merge re-unifies them so ``alembic upgrade head`` keeps a single
resolution path. No schema change.
"""

from typing import Sequence, Union

from alembic import op

revision = "m3rge08"
down_revision: Union[str, Sequence[str], None] = (
    "aut5092_dev_veh_type",
    "g7h8i9j0k1l3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
