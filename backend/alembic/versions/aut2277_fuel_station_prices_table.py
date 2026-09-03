"""Rename SERVO SPY ``fuel_prices`` -> ``fuel_station_prices`` (AUT-2277).

The SERVO SPY (AUT-1817) price row and the NSW snapshot (AUT-1813) row
both used to claim ``__tablename__ = "fuel_prices"`` with incompatible
column sets, and ``f0a1b2c3d4e5`` created a ``fuel_prices`` table with the
SERVO SPY shape. The follow-up rename was never written, so any stack that
ran ``f0a1b2c3d4e5`` before AUT-2277 has the SERVO SPY table sitting under
``fuel_prices`` while the NSW snapshot row is also (correctly) in
``fuel_prices`` (with a different shape). The two paths collide at SQLAlchemy
metadata load time even though only one of them actually has rows.

Resolution: the SERVO SPY model (``app.models.fuel_station.FuelStationPrice``)
now lives in ``fuel_station_prices``. This revision:

* If ``fuel_station_prices`` already exists -> no-op (fresh deploys got the
  right name from ``f0a1b2c3d4e5``).
* Else if ``fuel_prices`` exists with the SERVO SPY shape (has a ``station_id``
  FK column) -> rename it to ``fuel_station_prices``.
* Else (no servo-spy data ever ingested) -> create ``fuel_station_prices``
  fresh, with its FK + indexes, so a future ingest can write into it.

The NSW-snapshot ``fuel_prices`` table (state+station_code+fuel_type unique)
is left untouched. The new ORM model ``FuelStationPrice`` points at the new
table; the existing ``FuelPrice`` snapshot model still points at
``fuel_prices``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2277_fuel_station_prices_table"
down_revision: Union[str, None] = "aut1859_fuel_price_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _inspect():
    if not _online():
        return None
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    insp = _inspect()
    if insp is None:
        return False
    return name in insp.get_table_names()


def _fuel_prices_is_servo_shape() -> bool:
    """True if ``fuel_prices`` has the SERVO SPY FK column ``station_id``.

    The NSW snapshot shape has ``state`` / ``station_code`` instead. They are
    mutually exclusive on any real schema.
    """
    insp = _inspect()
    if insp is None or not _has_table("fuel_prices"):
        return False
    cols = {c["name"] for c in insp.get_columns("fuel_prices")}
    return "station_id" in cols and "state" not in cols


def upgrade() -> None:
    if _has_table("fuel_station_prices"):
        return
    if _has_table("fuel_prices") and _fuel_prices_is_servo_shape():
        op.rename_table("fuel_prices", "fuel_station_prices")
        # The original migration created an index named for the old table;
        # rename it so deployments that drop+recreate can find the right name.
        if _online():
            insp = sa.inspect(op.get_bind())
            indexes = {ix["name"] for ix in insp.get_indexes("fuel_station_prices")}
            if "ix_fuel_prices_station_fuel" in indexes and "ix_fuel_station_prices_station_fuel" not in indexes:
                op.execute("ALTER INDEX ix_fuel_prices_station_fuel RENAME TO ix_fuel_station_prices_station_fuel")
        return
    if not _has_table("fuel_stations"):
        # Defensive: a stack with the SERVO SPY logic but no stations table is
        # broken anyway, but creating the FK target keeps the migration valid
        # for an empty / partial bootstrap DB.
        op.create_table(
            "fuel_stations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source", sa.String(16), nullable=False, index=True),
            sa.Column("source_id", sa.String(64), nullable=False),
            sa.Column("brand", sa.String(64), nullable=True, index=True),
            sa.Column("lat", sa.Float(), nullable=True),
            sa.Column("lon", sa.Float(), nullable=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("address", sa.String(512), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("source", "source_id", name="uq_fuel_station_source"),
        )
    op.create_table(
        "fuel_station_prices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("station_id", sa.String(36), sa.ForeignKey("fuel_stations.id"), nullable=False, index=True),
        sa.Column("fuel_type", sa.String(16), nullable=False, index=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_fuel_station_prices_station_fuel",
        "fuel_station_prices",
        ["station_id", "fuel_type"],
    )


def downgrade() -> None:
    # Best-effort: do not invent a ``fuel_prices`` table on the way down.
    if not _online():
        return
    if _has_table("fuel_station_prices") and not _has_table("fuel_prices"):
        op.rename_table("fuel_station_prices", "fuel_prices")
