"""Create fuel_price_snapshots table (AUT-3005).

PR #457 updated store_nsw_prices to write to FuelPriceSnapshot but no
Alembic migration creates that table.  The aut1859 migration only adds
previous_price/previous_price_at to fuel_prices (wrong target).

This migration creates fuel_price_snapshots with every column defined in
app.models.fuel_price.FuelPriceSnapshot, plus the unique constraint
uq_fuel_price_snapshot_station_fuel on (state, station_code, fuel_type).
DDL is guarded with _has_table so create_all bootstrap is a no-op.

Anchored after aut1859_fuel_price_alerts (via current head m3rge06 which
descends from aut1859).  Downgrade drops the table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut3005_fuel_price_snapshots"
down_revision: Union[str, Sequence[str], None] = "m3rge06"
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
    if not _has_table("fuel_price_snapshots"):
        op.create_table(
            "fuel_price_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("state", sa.String(8), nullable=False),
            sa.Column("station_code", sa.String(32), nullable=False),
            sa.Column("station_name", sa.String(160), nullable=True),
            sa.Column("brand", sa.String(80), nullable=True),
            sa.Column("address", sa.String(240), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("fuel_type", sa.String(16), nullable=False),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(8), server_default="AUD"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "fetched_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("previous_price", sa.Float(), nullable=True),
            sa.Column("previous_price_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "state", "station_code", "fuel_type",
                name="uq_fuel_price_snapshot_station_fuel",
            ),
            sa.Index("ix_fuel_snap_state", "state"),
            sa.Index("ix_fuel_snap_station", "state", "station_code"),
            sa.Index("ix_fuel_snap_fuel", "fuel_type"),
        )


def downgrade() -> None:
    if _has_table("fuel_price_snapshots"):
        op.drop_table("fuel_price_snapshots")
