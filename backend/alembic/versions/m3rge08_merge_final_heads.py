"""merge aut5092_dev_veh_type + g7h8i9j0k1l3 heads (AUT-380)

aut5092_dev_veh_type (device vehicle_type repair, descends through aut4925/m3rge01/aut1813)
and g7h8i9j0k1l3 (pgvector remaining embeddings, descends through h1i2j3k4l5m6 hnsw indexes)
were both merged straight into main, leaving two script-tree heads. Alembic then
refuses ``upgrade head`` and every deploy silently fell back to ``create_all``
(same failure class as AUT-675 / AUT-918). This merge re-unifies them so the
AUT-702 single-head guard passes. No schema change.
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