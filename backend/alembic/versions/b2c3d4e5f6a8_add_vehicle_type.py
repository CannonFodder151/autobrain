"""add_vehicle_type

Revision ID: b2c3d4e5f6a8
Revises: a9b8c7d6e5f4
Create Date: 2026-08-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vehicles', sa.Column('vehicle_type', sa.String(length=20),
                                        nullable=False, server_default='car'))


def downgrade() -> None:
    op.drop_column('vehicles', 'vehicle_type')
