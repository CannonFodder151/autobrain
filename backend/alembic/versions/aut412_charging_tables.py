"""charging-station tables for Electric Spy (AUT-412)

Revision ID: aut412_charging_tables
Revises: m3rge03_merge_build_flags_and_devices
Create Date: 2026-11-11 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aut412_charging_tables"
down_revision: Union[str, None] = "m3rge03_merge_build_flags_and_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # charging_stations
    op.create_table(
        "charging_stations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("brand", sa.String(64), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("connector_types", sa.String(128), nullable=True),
        sa.Column("max_power_kw", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_charging_stations_source", "charging_stations", ["source"])
    op.create_index("ix_charging_stations_source_id", "charging_stations", ["source_id"])
    op.create_index("ix_charging_stations_brand", "charging_stations", ["brand"])

    # charging_prices
    op.create_table(
        "charging_prices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("station_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(16), nullable=False),
        sa.Column("price_per_kwh", sa.Float(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(16), nullable=True),
        sa.Column("arbitration_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["charging_stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_charging_prices_station_id", "charging_prices", ["station_id"])
    op.create_index("ix_charging_prices_connector_type", "charging_prices", ["connector_type"])
    op.create_index("ix_charging_prices_source_id", "charging_prices", ["source_id"])

    # charging_price_arbitrations
    op.create_table(
        "charging_price_arbitrations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("station_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(16), nullable=False),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(16), nullable=False),
        sa.Column("price_per_kwh", sa.Float(), nullable=False),
        sa.Column("arbitration_score", sa.Float(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["charging_stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id", "connector_type", "day",
            name="uq_charging_arbitration_station_connector_day",
        ),
    )
    op.create_index("ix_charging_price_arbitrations_station_id", "charging_price_arbitrations", ["station_id"])
    op.create_index("ix_charging_price_arbitrations_connector_type", "charging_price_arbitrations", ["connector_type"])

    # AUT-412: preferred connector type on vehicles
    op.add_column(
        "vehicles",
        sa.Column("preferred_connector_type", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehicles", "preferred_connector_type")
    op.drop_index("ix_charging_price_arbitrations_connector_type", table_name="charging_price_arbitrations")
    op.drop_index("ix_charging_price_arbitrations_station_id", table_name="charging_price_arbitrations")
    op.drop_table("charging_price_arbitrations")
    op.drop_index("ix_charging_prices_source_id", table_name="charging_prices")
    op.drop_index("ix_charging_prices_connector_type", table_name="charging_prices")
    op.drop_index("ix_charging_prices_station_id", table_name="charging_prices")
    op.drop_table("charging_prices")
    op.drop_index("ix_charging_stations_brand", table_name="charging_stations")
    op.drop_index("ix_charging_stations_source_id", table_name="charging_stations")
    op.drop_index("ix_charging_stations_source", table_name="charging_stations")
    op.drop_table("charging_stations")