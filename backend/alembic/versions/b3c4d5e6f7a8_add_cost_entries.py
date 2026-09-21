"""add_cost_entries

Revision ID: b3c4d5e6f7a8
Revises: None (new feature)
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cost_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vehicle_id', sa.String(36), sa.ForeignKey('vehicles.id'), index=True),
        sa.Column('category', sa.String(32), nullable=False, index=True),
        sa.Column('amount', sa.Float, nullable=False),
        sa.Column('currency', sa.String(8), server_default='AUD'),
        sa.Column('date', sa.Date, nullable=False, index=True),
        sa.Column('odometer_km', sa.Integer, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('vendor', sa.String(255), nullable=True),
        sa.Column('receipt_id', sa.String(36), sa.ForeignKey('receipts.id'), nullable=True),
        sa.Column('track_name', sa.String(255), nullable=True),
        sa.Column('laps_completed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_cost_entries_vehicle_category', 'cost_entries', ['vehicle_id', 'category'])
    op.create_index('ix_cost_entries_vehicle_date', 'cost_entries', ['vehicle_id', 'date'])


def downgrade() -> None:
    op.drop_table('cost_entries')