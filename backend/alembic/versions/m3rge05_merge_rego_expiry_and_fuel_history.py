"""merge rego-expiry + fuel-history heads

m3rge05: unifies the two heads left after the AUT-2375 fuel-history-index
branch (``aut2375_fuel_history_index``) and the AUT-2416 rego-expiry
branch (``a1b2c3d4e5f8``) both landed on main. No-op DDL — both branches
are already applied on every deployed DB; this just restores a single
alembic head so ``alembic upgrade head`` works at bootstrap instead of
falling back to ``create_all`` (AUT-702 single-head guard).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge05"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f8", "aut2375_fuel_history_index")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass