"""AUT-2386: source-arbitration columns + per-day winner table.

Some stations appear in multiple government feeds (Ampol/BP/Costco in NSW
FuelCheck + SAFPIS + QLD Fuel Prices). We need a deterministic winner per
(station, fuel_type, day) so the /history chart and the live fuel list are
consistent across feeds.

This migration:

* Adds ``fuel_prices.source_id`` and ``fuel_prices.arbitration_score`` so each
  raw observation row remembers which feed produced it and its score under
  the rule. Nullable on purpose: rows ingested before this column existed
  keep working.
* Creates ``fuel_price_arbitrations`` (one row per
  station + fuel_type + day) with the chosen source/price/score. The
  Celery ingest task writes it via ``app.services.fuel_feeds.arbitrate_*``.

All DDL is guarded so a DB already at target (e.g. create_all bootstrap) is
a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2386_source_arbitration"
down_revision: Union[str, Sequence[str], None] = "aut1859_fuel_price_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, col: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return col in {c["name"] for c in insp.get_columns(table)}


def _has_table(table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return table in set(insp.get_table_names())


def _has_index(name: str, table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if _has_column("fuel_prices", "source_id"):
        return
    op.add_column(
        "fuel_prices",
        sa.Column("source_id", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "fuel_prices",
        sa.Column("arbitration_score", sa.Float(), nullable=True),
    )
    if not _has_index("ix_fuel_prices_source_id", "fuel_prices"):
        op.create_index(
            "ix_fuel_prices_source_id", "fuel_prices", ["source_id"]
        )

    if _has_table("fuel_price_arbitrations"):
        return
    op.create_table(
        "fuel_price_arbitrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("station_id", sa.String(length=36), sa.ForeignKey("fuel_stations.id"), nullable=False),
        sa.Column("fuel_type", sa.String(length=16), nullable=False),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("arbitration_score", sa.Float(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "station_id", "fuel_type", "day",
            name="uq_fuel_arbitration_station_fuel_day",
        ),
    )
    op.create_index(
        "ix_fuel_price_arbitrations_station_fuel",
        "fuel_price_arbitrations",
        ["station_id", "fuel_type"],
    )
    op.create_index(
        "ix_fuel_price_arbitrations_day",
        "fuel_price_arbitrations",
        ["day"],
    )


def downgrade() -> None:
    if _online():
        if _has_table("fuel_price_arbitrations"):
            op.drop_index("ix_fuel_price_arbitrations_day", table_name="fuel_price_arbitrations")
            op.drop_index("ix_fuel_price_arbitrations_station_fuel", table_name="fuel_price_arbitrations")
            op.drop_table("fuel_price_arbitrations")
        if _has_column("fuel_prices", "arbitration_score"):
            op.drop_column("fuel_prices", "arbitration_score")
        if _has_column("fuel_prices", "source_id"):
            if _has_index("ix_fuel_prices_source_id", "fuel_prices"):
                op.drop_index("ix_fuel_prices_source_id", table_name="fuel_prices")
            op.drop_column("fuel_prices", "source_id")
