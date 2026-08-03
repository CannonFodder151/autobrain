"""add_service_status_and_items

Revision ID: d4e5f6a7b8c9
Revises: f6b62c70c0c4
Create Date: 2026-08-03 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'f6b62c70c0c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('service_records', sa.Column('status', sa.String(length=20), nullable=False, server_default='completed'))
    op.add_column('service_records', sa.Column('completed_date', sa.Date(), nullable=True))
    op.add_column('service_records', sa.Column('steps', sa.Text(), nullable=True))
    op.add_column('service_items', sa.Column('kind', sa.String(length=20), nullable=False, server_default='item'))
    op.add_column('service_items', sa.Column('part_no', sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column('service_items', 'part_no')
    op.drop_column('service_items', 'kind')
    op.drop_column('service_records', 'steps')
    op.drop_column('service_records', 'completed_date')
    op.drop_column('service_records', 'status')
