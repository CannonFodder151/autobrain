"""Add vehicles.is_financed (AUT-3588).

Adds a boolean ``is_financed`` column to ``vehicles`` so the frontend can
conditionally show a Finance button in the home feature grid. Defaults to
``False`` for all existing and new rows.

Parent: AUT-3571.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut3588_vehicle_is_financed"
down_revision: Union[str, Sequence[str], None] = "aut3447_passkey_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        if not _column_exists(batch, "is_financed"):
            batch.add_column(
                sa.Column(
                    "is_financed",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_column("is_financed")


def _column_exists(batch: "op.BatchOperations", name: str) -> bool:
    try:
        inspector = op.get_context().inspector
        return name in [c["name"] for c in inspector.get_columns("vehicles")]
    except Exception:
        return False
