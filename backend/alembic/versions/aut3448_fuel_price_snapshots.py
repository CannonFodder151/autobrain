"""AUT-3005: create fuel_price_snapshots table for NSW Fuel API cache.

The FuelPriceSnapshot model (fuel_price_snapshots table) was previously
created by the bootstrap create_all fallback but never by an explicit
migration. This migration adds the table idempotently so fresh databases
and CI environments have the schema guaranteed without relying on the
bootstrap fallback. Anchored after aut1859_fuel_price_alerts conceptually;
added at current head aut3447 in practice.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut3448_fuel_price_snapshots"
down_revision: Union[str, None] = "aut3447_passkey_credentials"
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
    if _has_table("fuel_price_snapshots"):
        return  # already present (e.g. created by bootstrap create_all)

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
        sa.Column("currency", sa.String(8), nullable=False, server_default="AUD"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("previous_price", sa.Float(), nullable=True),
        sa.Column("previous_price_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fuel_price_snapshots_state", "fuel_price_snapshots", ["state"])
    op.create_index("ix_fuel_price_snapshots_station_code", "fuel_price_snapshots", ["station_code"])
    op.create_index("ix_fuel_price_snapshots_fuel_type", "fuel_price_snapshots", ["fuel_type"])
    op.create_unique_constraint(
        "uq_fuel_price_snapshot_station_fuel",
        "fuel_price_snapshots",
        ["state", "station_code", "fuel_type"],
    )

def downgrade() -> None:
    if not _online() or not _has_table("fuel_price_snapshots"):
        return
    # Check if the constraint exists before dropping
    insp = sa.inspect(op.get_bind())
    constraints = {c["name"] for c in insp.get_unique_constraints("fuel_price_snapshots")}
    if "uq_fuel_price_snapshot_station_fuel" in constraints:
        op.drop_constraint("uq_fuel_price_snapshot_station_fuel", "fuel_price_snapshots", type_="unique")
    op.drop_index("ix_fuel_price_snapshots_fuel_type", table_name="fuel_price_snapshots")
    op.drop_index("ix_fuel_price_snapshots_station_code", table_name="fuel_price_snapshots")
    op.drop_index("ix_fuel_price_snapshots_state", table_name="fuel_price_snapshots")
    op.drop_table("fuel_price_snapshots")
