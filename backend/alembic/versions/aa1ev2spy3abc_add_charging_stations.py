"""add charging_stations + charging_connectors (AUT-2435 Electric Spy)

Tables for cached Open Charge Map data. Mirrors the fuel_stations /
fuel_prices pattern: station registry + per-station connector/price records.

DDL ops guarded so DBs where create_all already applied apply cleanly.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aa1ev2spy3abc"
down_revision: Union[str, None] = "z2a3b4c5d6e7"
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
    if _has_table("charging_stations"):
        return
    op.create_table(
        "charging_stations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ocm_id", sa.Integer(), nullable=True, index=True),
        sa.Column("network", sa.String(64), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "charging_connectors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "station_id",
            sa.String(36),
            sa.ForeignKey("charging_stations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("connector_type", sa.String(32), nullable=False, index=True),
        sa.Column("max_power_kw", sa.Float(), nullable=True),
        sa.Column("cost_per_kwh", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("charging_connectors")
    op.drop_table("charging_stations")
