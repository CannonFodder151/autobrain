"""merge vehicle-type and token-lifecycle branches

The vehicle-type chain (b2c3d4e5f6a8) and the pgvector/share/token-lifecycle
chain (…e1f2a3b4c5d6 → h2j3k4l5m6n7) forked off e6f7a8b9c0d1, leaving two
alembic heads and breaking `alembic upgrade head` in the boot command. This
merge re-unifies them so both branches apply regardless of which one a given
database was stamped at. No schema change.

Revision ID: m3rge01
Revises: h2j3k4l5m6n7, b2c3d4e5f6a8
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'm3rge01'
down_revision: Union[str, Sequence[str], None] = ('h2j3k4l5m6n7', 'b2c3d4e5f6a8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
