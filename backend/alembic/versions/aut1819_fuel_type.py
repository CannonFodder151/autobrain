"""Merge outstanding heads and add vehicles.fuel_type (AUT-1819).

Unifies the six open heads on ``main`` (rego_state, stripe subscription,
vehicle shares, fuel stations/prices, social photo position, issue blog
tables) so ``alembic upgrade head`` resolves to a single path again
(regression guard in ``test_alembic_heads.py``). While here, add the
``fuel_type`` column the vehicle fuel-type dropdown persists against
(canonical tokens match ``feeds.DEFAULT_FUEL_TYPES``: E10/91/95/98/Diesel/LPG).

DDL is guarded so a DB already at target is a no-op (create_all fallback).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut1819_fuel_type"
down_revision: Union[str, Sequence[str], None] = (
    "aut1903_rego_state",
    "d5e6f7a8b9c0",
    "e1f2a3b4c5d6",
    "f0a1b2c3d4e5",
    "q1r2s3t4u5v6",
    "u1v2w3x4y5z6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        if not _column_exists(batch, "fuel_type"):
            batch.add_column(
                sa.Column("fuel_type", sa.String(length=16), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("vehicles") as batch:
        batch.drop_column("fuel_type")


def _column_exists(batch: "op.BatchOperations", name: str) -> bool:
    """True when ``name`` is already present on ``vehicles``.

    create_all-backed schemas (the bootstrap fallback used while the graph
    had multiple heads) may already carry the column, so guard against a
    duplicate-add instead of blindly running DDL.
    """
    try:
        inspector = op.get_context().inspector
        return name in [c["name"] for c in inspector.get_columns("vehicles")]
    except Exception:
        return False
