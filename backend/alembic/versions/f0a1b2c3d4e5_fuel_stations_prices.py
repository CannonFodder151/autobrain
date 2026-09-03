"""Add fuel price pipeline tables (Servo Spy, AUT-1817, AUT-2277).

Deterministic ingest targets for WA FuelWatch, NSW FuelCheck and QLD Fuel
Prices. No PostGIS column (Phase-1 vector store not applicable; radius queries
use a great-circle distance in Python, see ``app.services.fuel_feeds``).

AUT-2277: the price row used to live in ``fuel_prices`` with an FK to
``fuel_stations``, colliding with the AUT-1813 NSW snapshot row (state +
station_code unique) in the same table. The snapshot model still owns
``fuel_prices``; the servo-spy model now lives in its own
``fuel_station_prices`` table. Stacks that already ran this migration on the
old name are picked up by the follow-up ``aut2277_fuel_station_prices_table``
revision, which renames the leftover table. Fresh stacks get the right name
here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "sca0parts1cache0"
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
    if not _has_table("fuel_stations"):
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
    if not _has_table("fuel_station_prices"):
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
    if _online():
        op.drop_table("fuel_station_prices")
        op.drop_table("fuel_stations")
