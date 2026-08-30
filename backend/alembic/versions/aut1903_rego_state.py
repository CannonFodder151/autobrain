"""Add rego_state to vehicles (AUT-1903).

Parts lookup must use the state registered against the selected vehicle
(plate + state) instead of letting the user type a rego/state freehand.
Stores the registration state next to the existing ``rego`` column.

This revision merges the two open heads on ``main`` (``a1b7c3d4e5f7`` dongle
firmware and ``sca0parts1cache0`` SCA parts cache) so the graph stays
single-headed until AUT-1859's merge lands.

DDL guarded so a DB already at target is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut1903_rego_state"
down_revision: Union[str, Sequence[str], None] = (
    "a1b7c3d4e5f7",
    "sca0parts1cache0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        batch.add_column(
            sa.Column("rego_state", sa.String(length=8), nullable=True)
        )
    op.create_index(
        op.f("ix_vehicles_rego_state"), "vehicles", ["rego_state"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vehicles_rego_state"), table_name="vehicles")
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_column("rego_state")
