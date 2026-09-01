"""petrol price map cache (AUT-1813) + merge divergent embedding/cache heads

Adds nsw_fuel_prices (cached NSW Fuel API snapshot, one row per station+fuel type)
and nsw_fuel_price_poll_state (per-instance last-poll timestamp enforcing the
once-per-day-per-instance quota). DDL is guarded so DBs where the tables were
already created by bootstrap's create_all fallback apply cleanly as no-ops.

This also resolves the two pre-existing divergent heads
(h1i2j3k4l5m6 hnsw indexes + h1i2j3k4l5m7 market-listing cache) into a single
head so `alembic upgrade head` is unambiguous.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut1813_fuel_prices"
down_revision: Union[str, Sequence[str], None] = "aut1819_fuel_type"
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
    if not _has_table("nsw_fuel_prices"):
        op.create_table(
            "nsw_fuel_prices",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("state", sa.String(8), nullable=False),
            sa.Column("station_code", sa.String(32), nullable=False),
            sa.Column("station_name", sa.String(160), nullable=True),
            sa.Column("brand", sa.String(80), nullable=True),
            sa.Column("address", sa.String(240), nullable=True),
            sa.Column("latitude", sa.Float, nullable=True),
            sa.Column("longitude", sa.Float, nullable=True),
            sa.Column("fuel_type", sa.String(16), nullable=False),
            sa.Column("price", sa.Float, nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="AUD"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_nsw_fuel_prices_state", "nsw_fuel_prices", ["state"])
        op.create_index("ix_nsw_fuel_prices_station_code", "nsw_fuel_prices", ["station_code"])
        op.create_index("ix_nsw_fuel_prices_fuel_type", "nsw_fuel_prices", ["fuel_type"])
        op.create_unique_constraint(
            "uq_nsw_fuel_price_station_fuel", "nsw_fuel_prices", ["state", "station_code", "fuel_type"]
        )
    if not _has_table("nsw_fuel_price_poll_state"):
        op.create_table(
            "nsw_fuel_price_poll_state",
            sa.Column("instance_id", sa.String(120), primary_key=True),
            sa.Column("state", sa.String(8), primary_key=True),
            sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _has_table("nsw_fuel_prices"):
        if "uq_nsw_fuel_price_station_fuel" in {c["name"] for c in sa.inspect(op.get_bind()).get_unique_constraints("nsw_fuel_prices")}:
            op.drop_constraint("uq_nsw_fuel_price_station_fuel", "nsw_fuel_prices", type_="unique")
        op.drop_table("nsw_fuel_prices")
    if _has_table("nsw_fuel_price_poll_state"):
        op.drop_table("nsw_fuel_price_poll_state")