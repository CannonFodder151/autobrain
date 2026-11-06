"""merge aut5092_dev_veh_type + g7h8i9j0k1l3 heads (AUT-345)

aut5092_dev_veh_type (devices.vehicle_type repair) and
g7h8i9j0k1l3 (pgvector embeddings remaining) are both heads descending from
different branches. This merge re-unifies them so ``alembic upgrade head``
keeps a single resolution path (AUT-702 single-head guard). No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge08"
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
