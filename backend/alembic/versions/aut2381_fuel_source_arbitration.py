"""Multi-source fuel-price arbitration columns (AUT-2381).

Adds ``source`` (upstream id), ``best_source`` (arbitration winner),
``source_score`` (AUT-2381 score for the winner) and ``flag_reason`` (consistency
outlier note) to ``fuel_prices``. Backfills ``source`` from the station's
``fuel_stations.source`` so legacy rows remain useful after upgrade.

Deterministic, no AI, no data loss: every existing row keeps its id, station_id,
fuel_type, price and effective_at — we only add columns and an index.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut2381_fuel_source_arbitration"
down_revision: Union[str, None] = "aut2434_vehicle_powertrain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_col(table: str, col: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return col in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return any(idx["name"] == name for idx in insp.get_indexes(table))


def upgrade() -> None:
    if not _has_col("fuel_prices", "source"):
        op.add_column("fuel_prices", sa.Column("source", sa.String(16), nullable=True))
    if not _has_col("fuel_prices", "best_source"):
        op.add_column("fuel_prices", sa.Column("best_source", sa.String(16), nullable=True))
    if not _has_col("fuel_prices", "source_score"):
        op.add_column("fuel_prices", sa.Column("source_score", sa.Float(), nullable=True))
    if not _has_col("fuel_prices", "flag_reason"):
        op.add_column("fuel_prices", sa.Column("flag_reason", sa.String(64), nullable=True))

    if not _has_index("fuel_prices", "ix_fuel_prices_source"):
        op.create_index("ix_fuel_prices_source", "fuel_prices", ["source"])
    if not _has_index("fuel_prices", "ix_fuel_prices_best_source"):
        op.create_index("ix_fuel_prices_best_source", "fuel_prices", ["best_source"])

    # Backfill: legacy rows have no ``source`` set; the station knows which
    # upstream it came from, so copy that across so the UI's badges stay
    # meaningful for already-ingested data. Idempotent.
    if _online():
        op.execute(
            sa.text(
                "UPDATE fuel_prices AS p "
                "SET source = s.source "
                "FROM fuel_stations AS s "
                "WHERE p.station_id = s.id AND p.source IS NULL"
            )
        )


def downgrade() -> None:
    if _online():
        insp = sa.inspect(op.get_bind())
        for idx in ("ix_fuel_prices_best_source", "ix_fuel_prices_source"):
            if any(i["name"] == idx for i in insp.get_indexes("fuel_prices")):
                op.drop_index(idx, table_name="fuel_prices")
    for col in ("flag_reason", "source_score", "best_source", "source"):
        if _has_col("fuel_prices", col):
            op.drop_column("fuel_prices", col)
