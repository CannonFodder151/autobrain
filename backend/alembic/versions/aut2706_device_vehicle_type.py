"""add devices.vehicle_type (AUT-2706: EV mode + vehicle type detection)

The dongle classifies vehicle type from its first trip (0=unknown/1=ICE/2=EV/3=HEV/4=PHEV
via RPM vs pack_current hysteresis, 4=PHEV when EV detected and fuel level present)
and sends it to POST /devices/{id}/vehicle-type.
We store a canonical string label on the devices row.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2706_device_vehicle_type"
down_revision: Union[str, None] = "m3rge05"
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
    if _online() and _has_column("devices", "vehicle_type"):
        return  # already present
    op.add_column("devices", sa.Column("vehicle_type", sa.String(8), nullable=True))


def downgrade() -> None:
    if not _online() or not _has_column("devices", "vehicle_type"):
        return
    op.drop_column("devices", "vehicle_type")
