"""AUT-2375: index fuel_prices for 30-day history queries.

The /api/v1/fuel/stations/{id}/history endpoint filters by station_id + a
time-range cutoff and orders by (fuel_type, effective_at). The existing
``ix_fuel_prices_station_fuel`` covers the (station_id, fuel_type) prefix but
the effective_at ordering needs its own path. A composite
(station_id, fuel_type, effective_at) index serves both the equality filter
and the order-by without a sort step on the 30-day result set.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2375_fuel_history_index"
down_revision: Union[str, None] = "aut2381_fuel_source_arbitration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_index(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes("fuel_prices")}


def upgrade() -> None:
    if not _has_index("ix_fuel_prices_station_fuel_eff"):
            op.create_index(
                "ix_fuel_prices_station_fuel_eff",
                "fuel_prices",
                ["station_id", "fuel_type", "effective_at"],
            )


def downgrade() -> None:
    if _online():
        try:
            op.drop_index("ix_fuel_prices_station_fuel_eff", table_name="fuel_prices")
        except Exception:
            pass