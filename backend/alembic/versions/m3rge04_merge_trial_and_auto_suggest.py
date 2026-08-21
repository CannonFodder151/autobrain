"""merge trial flag + auto suggest heads

Merges t1a2b3c4d5e6 (has_had_trial) and b4c5d6e7f8a9 (auto_suggest_service)
so ``alembic upgrade head`` keeps a single resolution path.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge04"
down_revision: Union[str, Sequence[str], None] = ("t1a2b3c4d5e6", "b4c5d6e7f8a9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
