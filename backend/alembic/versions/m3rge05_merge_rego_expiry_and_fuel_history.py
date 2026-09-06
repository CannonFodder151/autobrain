"""merge rego-expiry-days + fuel-history-index heads (AUT-2677)

a1b2c3d4e5f8 (rego_expiry_days) and aut2375_fuel_history_index are both heads
descending from aut1859_fuel_price_alerts. This merge re-unifies them so
``alembic upgrade head`` keeps a single resolution path (AUT-702 single-head
guard). No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge05"
down_revision: Union[str, Sequence[str], None] = (
    "a1b2c3d4e5f8",
    "aut2375_fuel_history_index",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
