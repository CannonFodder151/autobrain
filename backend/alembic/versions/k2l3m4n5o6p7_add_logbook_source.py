"""logbook trip source (manual/obd_auto) for auto-recorded OBD trips

Revision ID: k2l3m4n5o6p7
Revises: m3rge01
Create Date: 2026-08-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k2l3m4n5o6p7'
down_revision: Union[str, None] = 'm3rge01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'logbook_entries',
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
    )


def downgrade() -> None:
    op.drop_column('logbook_entries', 'source')
