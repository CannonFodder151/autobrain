"""Add vehicles.powertrain (AUT-2434).

Adds the ``powertrain`` column to ``vehicles`` so the API can distinguish
ICE / EV / HEV / PHEV vehicles. Stored as a constrained VARCHAR(8) (rather
than a Postgres ENUM type) so future tokens can be added without a
type-migration dance. Pre-existing rows backfill to ``"ICE"`` — the
overwhelming historical default — and the model default covers all new
writes. DDL is guarded so a DB already at target (e.g. create_all
bootstrap) is a no-op.

Parent: AUT-2420.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut2434_vehicle_powertrain"
down_revision: Union[str, Sequence[str], None] = "aut1859_fuel_price_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        if not _column_exists(batch, "powertrain"):
            batch.add_column(
                sa.Column(
                    "powertrain",
                    sa.String(length=8),
                    nullable=False,
                    server_default="ICE",
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_column("powertrain")


def _column_exists(batch: "op.BatchOperations", name: str) -> bool:
    """True when ``name`` is already present on ``vehicles``.

    create_all-backed schemas (the bootstrap fallback used while the graph
    had multiple heads) may already carry the column, so guard against a
    duplicate-add instead of blindly running DDL.
    """
    try:
        inspector = op.get_context().inspector
        return name in [c["name"] for c in inspector.get_columns("vehicles")]
    except Exception:
        return False