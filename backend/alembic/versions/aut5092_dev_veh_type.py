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

AUT-5612: ``downgrade()`` used to drop ``vehicle_type`` whenever it merely
existed, which is a data-loss path on precisely the database this migration
exists to repair: on a create_all-built DB the column is *already there*, so
``upgrade()`` is a no-op that never created it and a rollback destroyed real
data. ``upgrade()`` now tags the column it adds with ``_MARKER`` and
``downgrade()`` drops only a column carrying that marker. A column without the
marker was not created here and is left alone.
"""

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut5092_dev_veh_type"
down_revision: Union[str, Sequence[str], None] = "aut3448_fuel_price_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Stamped on the column when this revision is the one that created it, so
# downgrade() can tell "ours" from "pre-existing drift".
_MARKER = "created-by-aut5092_dev_veh_type"


def _columns(table: str) -> list[dict[str, Any]]:
    if context.is_offline_mode():
        return []
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return []
    return insp.get_columns(table)


def upgrade() -> None:
    if "vehicle_type" not in {c["name"] for c in _columns("devices")}:
        op.add_column(
            "devices",
            sa.Column("vehicle_type", sa.String(8), nullable=True, comment=_MARKER),
        )


def downgrade() -> None:
    col = next((c for c in _columns("devices") if c["name"] == "vehicle_type"), None)
    if col is not None and col.get("comment") == _MARKER:
        op.drop_column("devices", "vehicle_type")