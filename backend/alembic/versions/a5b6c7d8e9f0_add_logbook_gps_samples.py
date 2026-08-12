"""add logbook_entries.gps_samples (trip route polyline, AUT-395)

Revision ID: a5b6c7d8e9f0
Revises: n4p5q6r7s8t9
Create Date: 2026-08-12 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'n4p5q6r7s8t9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('logbook_entries', sa.Column('gps_samples', sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column('logbook_entries', 'gps_samples')
