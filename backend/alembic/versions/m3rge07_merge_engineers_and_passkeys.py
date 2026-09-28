"""merge a3661engineers + aut3447_passkey_credentials heads (AUT-4259)

AUT-3661 (engineer marketplace, descends from z2a3b4c5d6e7 add_devices) and
AUT-3447 (passkey_credentials, descends from aut2705_phev_logbook_columns) were
both merged straight into main, leaving two script-tree heads. Alembic then
refuses ``upgrade head`` and every deploy silently fell back to ``create_all``
(same failure class as AUT-675 / AUT-918). This merge re-unifies them so the
AUT-702 single-head guard passes. No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge07"
down_revision: Union[str, Sequence[str], None] = (
    "a3661engineers",
    "aut3447_passkey_credentials",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
