"""add_notifications

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('vehicle_id', sa.String(36), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('discord_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('service_due_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('service_due_km', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('fuel_gap_km', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('discord_webhook_url', sa.Text(), nullable=True),
        sa.Column('fcm_token', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'vehicle_id', name='uq_notif_user_vehicle'),
    )
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vehicle_id', sa.String(36), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('channels', sa.String(100), nullable=False, server_default='email'),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('vehicle_id', 'kind', name='uq_notif_delivery_vehicle_kind'),
    )


def downgrade() -> None:
    op.drop_table('notification_deliveries')
    op.drop_table('notification_preferences')
