"""charging watchlist table for Electric Spy price alerts (AUT-412)

Revision ID: aut412_charging_watchlist
Revises: aut412_charging_tables
Create Date: 2026-11-11 05:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aut412_charging_watchlist"
down_revision: Union[str, None] = "aut412_charging_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "charging_price_watchlist",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("station_id", sa.String(36), nullable=False),
        sa.Column("connector_type", sa.String(16), nullable=False),
        sa.Column("target_price_per_kwh", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["charging_stations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "station_id", "connector_type",
            name="uq_charging_watch_user_station_connector",
        ),
    )
    op.create_index(
        "ix_charging_price_watchlist_user_id", "charging_price_watchlist", ["user_id"]
    )
    op.create_index(
        "ix_charging_price_watchlist_station_id", "charging_price_watchlist", ["station_id"]
    )
    op.create_index(
        "ix_charging_price_watchlist_connector_type", "charging_price_watchlist", ["connector_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_charging_price_watchlist_connector_type", table_name="charging_price_watchlist")
    op.drop_index("ix_charging_price_watchlist_station_id", table_name="charging_price_watchlist")
    op.drop_index("ix_charging_price_watchlist_user_id", table_name="charging_price_watchlist")
    op.drop_table("charging_price_watchlist")