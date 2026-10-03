"""logbook_entries AUT-2705 columns: repair schema drift left by the create_all fallback (AUT-5267)

Same drift class as ``aut5092_dev_veh_type`` (AUT-5092), different table.
Hosted (EP5) ran ``app.db.bootstrap``'s ``create_all`` fallback while its
``alembic_version`` sat at ``aut4925_missing_tables``. ``create_all`` builds the
schema from the ORM of that moment and never adds a column to an existing table,
so every column the model gained afterwards was skipped: hosted has no
``logbook_entries.vehicle_type`` (nor its AUT-2705 siblings) even though the
model and the ``aut2705_phev_logbook_columns`` migration both declare them.

``serialize_all`` selects whole tables, so the hourly off-site backup died with
``UndefinedColumnError: column logbook_entries.vehicle_type does not exist`` on
every run from the 2026-10-02 19:43Z deploy onwards.

Idempotent: adds each column only when it is missing, so it is a no-op on any
database that already has it (dev, demo, default, and hosted after this runs).

Revision ID: aut5267_logbook_veh_type (23 chars — ``alembic_version.version_num``
is ``varchar(32)``, see AUT-5122)
Revises: aut5092_dev_veh_type
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut5267_logbook_veh_type"
down_revision: Union[str, Sequence[str], None] = "aut5092_dev_veh_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Column name -> type, exactly as declared in aut2705_phev_logbook_columns.
_AUT2705_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "vehicle_type": sa.String(8),
    "ev_distance_km": sa.Float(),
    "ice_distance_km": sa.Float(),
    "charge_added_kwh": sa.Float(),
}


def _has_column(table: str, column: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return table in insp.get_table_names() and column in {
        c["name"] for c in insp.get_columns(table)
    }


def upgrade() -> None:
    for name, col_type in _AUT2705_COLUMNS.items():
        if not _has_column("logbook_entries", name):
            op.add_column("logbook_entries", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name in _AUT2705_COLUMNS:
        if _has_column("logbook_entries", name):
            op.drop_column("logbook_entries", name)