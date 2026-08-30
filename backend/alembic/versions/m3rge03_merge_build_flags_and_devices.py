"""merge build-flags + devices heads

m3rge03: unifies the two heads left after renumbering add_devices
(z2a3b4c5d6e7 from a1b2c3d4e5f6). No-op DDL — both branches are already
applied on every deployed DB; this just restores a single alembic head so
``alembic upgrade head`` works at bootstrap.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge03"
down_revision: Union[str, Sequence[str], None] = ("w5x6y7z8a9b0", "z2a3b4c5d6e7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
