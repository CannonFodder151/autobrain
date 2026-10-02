"""devices.vehicle_type: repair schema drift left by the aut4925 create_all fallback (AUT-5092)

Hosted (EP5) was stamped at `aut4925_missing_tables`, but `devices` predates
`aut2706_device_vehicle_type` in the *applied* DDL: every boot fell back to
`create_all` (SQLAlchemy never adds columns to an existing table), so the
aut2706 ALTER never ran. The ORM expects the column, so any query touching
`devices` — including the hourly backup serialization — died with
`UndefinedColumnError: column devices.vehicle_type does not exist`.

Idempotent: no-op when the table or column is already there.

Revision ID: aut5092_dev_veh_type
Revises: aut3448_fuel_price_snapshots
Create Date: 2026-10-02

AUT-5122: the revision id was ``aut5092_device_vehicle_type_repair`` (34 chars),
but ``alembic_version.version_num`` is ``varchar(32)`` — the stamp raised
``StringDataRightTruncationError``, bootstrap fell back to ``create_all`` and this
repair never applied. Ids must stay <= 32 chars (guarded by
``tests/test_alembic_heads.py::test_alembic_revision_ids_fit_version_column``).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut5092_dev_veh_type"
down_revision: Union[str, Sequence[str], None] = "aut3448_fuel_price_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return table in insp.get_table_names() and column in {
        c["name"] for c in insp.get_columns(table)
    }


def upgrade() -> None:
    if not _has_column("devices", "vehicle_type"):
        op.add_column("devices", sa.Column("vehicle_type", sa.String(8), nullable=True))


def downgrade() -> None:
    if _has_column("devices", "vehicle_type"):
        op.drop_column("devices", "vehicle_type")