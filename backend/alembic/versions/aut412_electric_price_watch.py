"""Electric Spy: charging station price snapshots + watchlist (AUT-412 + AUT-466).

Adds:
- charging_station_price_snapshots — cached price snapshots for EV charging
  stations, one row per (station_id, connector_type). Includes previous_price
  for day-over-day % change computation.
- charging_station_price_watchlist — the user's per-station+connector-type
  favourites (Electric Spy watchlist), with direction and % threshold for alerts.

Depends-on: m3rge08 (latest main head at time of writing).
DDL is guarded so a DB already at target is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut412_electric_price_watch"
down_revision: Union[str, Sequence[str], None] = "m3rge08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # --- charging_station_price_snapshots ---
    if not _has_table("charging_station_price_snapshots"):
        op.create_table(
            "charging_station_price_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("station_id", sa.String(64), nullable=False, index=True),
            sa.Column("station_name", sa.String(160), nullable=True),
            sa.Column("brand", sa.String(80), nullable=True),
            sa.Column("address", sa.String(240), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("connector_type", sa.String(32), nullable=False, index=True),
            sa.Column("price_per_kwh", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(8), nullable=False, server_default="AUD"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("previous_price", sa.Float(), nullable=True),
            sa.Column("previous_price_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "station_id", "connector_type",
                name="uq_charging_price_snapshot_station_connector",
            ),
        )

    # --- charging_station_price_watchlist ---
    if not _has_table("charging_station_price_watchlist"):
        op.create_table(
            "charging_station_price_watchlist",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("station_id", sa.String(64), nullable=False, index=True),
            sa.Column("station_name", sa.String(160), nullable=True),
            sa.Column("brand", sa.String(80), nullable=True),
            sa.Column("connector_type", sa.String(32), nullable=False, index=True),
            sa.Column("direction", sa.String(8), nullable=False, server_default="both"),
            sa.Column("threshold_pct", sa.Float(), nullable=False, server_default="5.0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id", "station_id", "connector_type",
                name="uq_charging_watch_user_station_connector",
            ),
        )


def downgrade() -> None:
    if _has_table("charging_station_price_watchlist"):
        op.drop_table("charging_station_price_watchlist")
    if _has_table("charging_station_price_snapshots"):
        op.drop_table("charging_station_price_snapshots")