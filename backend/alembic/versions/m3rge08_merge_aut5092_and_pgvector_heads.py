"""merge aut5092_dev_veh_type + g7h8i9j0k1l3 heads (AUT-225)"""
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
