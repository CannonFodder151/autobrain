"""Servo-spy fuel price alerts (AUT-1859) + notification-scope extension.

Adds:
- fuel_price_snapshots.previous_price / previous_price_at — the last *distinct*
  price, so day-over-day % moves are computed deterministically (no history
  table). (Table renamed from fuel_prices to fuel_price_snapshots to avoid
  colliding with the AUT-1817 Servo Spy fuel_prices table; see
  aut1813_fuel_prices.)
- fuel_price_watchlist — the user's per-station+fuel-type favourites, the
  direction they care about, and the % threshold that triggers an alert.
- notification_preferences.vehicle_id made nullable + a partial unique index
  (uq_notif_user_global) so a single user-global preference row exists for
  vehicle-independent alerts (serves AUT-1859 fuel price alerts).
- notification_deliveries: user_id column (nullable) + vehicle_id nullable +
  a partial unique index (uq_notif_delivery_user_kind) for dedupe of user alerts.

Merges the AUT-1813 chain with the current main head aut1819_fuel_type so
`alembic upgrade head` resolves to a single path again (AUT-702 single-head
guard).

Depends-on: aut1813_fuel_prices + aut1819_fuel_type. DDL is guarded so a DB
already at target (e.g. create_all bootstrap) is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut1859_fuel_price_alerts"
down_revision: Union[str, Sequence[str], None] = (
    "aut1813_fuel_prices",
    "aut1819_fuel_type",
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


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # --- fuel_prices: day-over-day basis ---
    if not _has_column("fuel_prices", "previous_price"):
        op.add_column("fuel_prices", sa.Column("previous_price", sa.Float(), nullable=True))
    if not _has_column("fuel_prices", "previous_price_at"):
        op.add_column(
            "fuel_prices", sa.Column("previous_price_at", sa.DateTime(timezone=True), nullable=True)
        )

    # --- fuel_price_watchlist ---
    if not _has_table("fuel_price_watchlist"):
        op.create_table(
            "fuel_price_watchlist",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("state", sa.String(8), nullable=False),
            sa.Column("station_code", sa.String(32), nullable=False),
            sa.Column("station_name", sa.String(160), nullable=True),
            sa.Column("brand", sa.String(80), nullable=True),
            sa.Column("fuel_type", sa.String(16), nullable=False),
            sa.Column("direction", sa.String(8), nullable=False, server_default="both"),
            sa.Column("threshold_pct", sa.Float(), nullable=False, server_default="5.0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id", "state", "station_code", "fuel_type",
                name="uq_fuel_watch_user_station_fuel",
            ),
            sa.Index("ix_fuel_watch_user", "user_id"),
            sa.Index("ix_fuel_watch_station", "state", "station_code", "fuel_type"),
        )

    # --- notification_preferences: nullable vehicle_id + user-global singleton ---
    if _has_table("notification_preferences"):
        if _has_column("notification_preferences", "vehicle_id") and not _has_column(
            "notification_preferences", "_vehicle_id_marker"
        ):
            # make vehicle_id nullable (existing rows stay; new global rows use NULL)
            op.alter_column(
                "notification_preferences", "vehicle_id",
                existing_type=sa.String(36), nullable=True,
            )
        # partial unique index on user_id for the single user-global row.
        idx = sa.inspect(op.get_bind()).get_indexes("notification_preferences") or []
        names = {i.get("name") for i in idx}
        if "uq_notif_user_global" not in names:
            if is_pg:
                op.execute(
                    "CREATE UNIQUE INDEX uq_notif_user_global "
                    "ON notification_preferences (user_id) "
                    "WHERE vehicle_id IS NULL"
                )
            else:
                # SQLite: emulate single-global by a generated column-free unique on user_id;
                # only one NULL vehicle_id per user in practice (enforced in-app).
                op.create_index("uq_notif_user_global", "notification_preferences", ["user_id"], unique=True)

    # --- notification_deliveries: user_id + nullable vehicle_id + user dedupe ---
    if _has_table("notification_deliveries"):
        if not _has_column("notification_deliveries", "user_id"):
            op.add_column("notification_deliveries", sa.Column("user_id", sa.String(36), nullable=True))
            op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
        if _has_column("notification_deliveries", "vehicle_id"):
            op.alter_column(
                "notification_deliveries", "vehicle_id",
                existing_type=sa.String(36), nullable=True,
            )
        idx = sa.inspect(op.get_bind()).get_indexes("notification_deliveries") or []
        names = {i.get("name") for i in idx}
        if "uq_notif_delivery_user_kind" not in names:
            if is_pg:
                op.execute(
                    "CREATE UNIQUE INDEX uq_notif_delivery_user_kind "
                    "ON notification_deliveries (user_id, kind) "
                    "WHERE vehicle_id IS NULL"
                )
            else:
                op.create_index(
                    "uq_notif_delivery_user_kind",
                    "notification_deliveries",
                    ["user_id", "kind"],
                    unique=True,
                )


def downgrade() -> None:
    if _has_index("notification_deliveries", "uq_notif_delivery_user_kind"):
        op.drop_index("uq_notif_delivery_user_kind", table_name="notification_deliveries")
    if _has_table("notification_deliveries") and _has_column("notification_deliveries", "user_id"):
        op.drop_column("notification_deliveries", "user_id")
    if _has_column("notification_deliveries", "vehicle_id"):
        op.alter_column(
            "notification_deliveries", "vehicle_id", existing_type=sa.String(36), nullable=False
        )

    if _has_index("notification_preferences", "uq_notif_user_global"):
        op.drop_index("uq_notif_user_global", table_name="notification_preferences")
    if _has_column("notification_preferences", "vehicle_id"):
        op.alter_column(
            "notification_preferences", "vehicle_id", existing_type=sa.String(36), nullable=False
        )

    if _has_table("fuel_price_watchlist"):
        op.drop_table("fuel_price_watchlist")

    if _has_column("fuel_prices", "previous_price_at"):
        op.drop_column("fuel_prices", "previous_price_at")
    if _has_column("fuel_prices", "previous_price"):
        op.drop_column("fuel_prices", "previous_price")


def _has_index(table: str, index: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return index in {i["name"] for i in (insp.get_indexes(table) or [])}
