"""add electricity_logs (AUT-2436)

Mirror of ``fuel_logs`` for EV charging sessions: kWh in, cost, $/kWh, and
chained km/kWh efficiency. Same ownership + odometer chaining as fuel so
the UX is a drop-in replacement for EVs.

DDL is guarded so a DB already at target (created_all fallback) applies
cleanly as a no-op (AUT-510 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2436_electricity_logs"
# Merge revision: attaches after BOTH open heads on main (aut2434 and
# aut2375). aut2375 -> aut2381 -> aut2434, but main still exposes two heads
# (aut2375 + aut2434) at the merge-base, so this down_revision list re-unifies
# them into a single head (see also aut1903_rego_state merge pattern).
down_revision: Union[str, Sequence[str], None] = (
    "aut2434_vehicle_powertrain",
    "aut2375_fuel_history_index",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _has_table("electricity_logs"):
        op.create_table(
            "electricity_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("charge_date", sa.Date, nullable=False),
            sa.Column("odometer_km", sa.Integer, nullable=False),
            sa.Column("kwh", sa.Float, nullable=False),
            sa.Column("price_per_kwh", sa.Float, nullable=False),
            sa.Column("total_cost", sa.Float, nullable=False),
            sa.Column("is_full_charge", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("distance_km", sa.Float, nullable=True),
            sa.Column("km_per_kwh", sa.Float, nullable=True),
            sa.Column("cost_per_km", sa.Float, nullable=True),
            sa.Column("receipt_id", sa.String(36), sa.ForeignKey("receipts.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_electricity_logs_vehicle_id", "electricity_logs", ["vehicle_id"])
        op.create_index("ix_electricity_logs_charge_date", "electricity_logs", ["charge_date"])


def downgrade() -> None:
    if _has_table("electricity_logs"):
        op.drop_table("electricity_logs")
