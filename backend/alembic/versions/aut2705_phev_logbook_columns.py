"""add PHEV columns to logbook_entries (AUT-2705)

Adds vehicle_type, ev_distance_km, ice_distance_km, and charge_added_kwh
to logbook_entries for EV/HEV/PHEV trip breakdown. Existing rows default
vehicle_type to NULL (unknown/unset) — the dongle sets it on new trips.

Parent: AUT-2437.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2705_phev_logbook_columns"
down_revision: Union[str, Sequence[str], None] = "m3rge06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, col: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if _online() and _has_column("logbook_entries", "vehicle_type"):
        return  # already present (create_all bootstrap)
    op.add_column("logbook_entries", sa.Column("vehicle_type", sa.String(8), nullable=True))
    op.add_column("logbook_entries", sa.Column("ev_distance_km", sa.Float, nullable=True))
    op.add_column("logbook_entries", sa.Column("ice_distance_km", sa.Float, nullable=True))
    op.add_column("logbook_entries", sa.Column("charge_added_kwh", sa.Float, nullable=True))


def downgrade() -> None:
    if not _online():
        return
    if _has_column("logbook_entries", "charge_added_kwh"):
        op.drop_column("logbook_entries", "charge_added_kwh")
    if _has_column("logbook_entries", "ice_distance_km"):
        op.drop_column("logbook_entries", "ice_distance_km")
    if _has_column("logbook_entries", "ev_distance_km"):
        op.drop_column("logbook_entries", "ev_distance_km")
    if _has_column("logbook_entries", "vehicle_type"):
        op.drop_column("logbook_entries", "vehicle_type")
