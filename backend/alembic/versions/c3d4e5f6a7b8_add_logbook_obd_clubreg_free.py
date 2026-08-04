"""logbook, obd, club reg, free tier, fuel receipt, diagnostics resolve

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('free_account', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('obd_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('obd_auto_connect', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    op.add_column('vehicles', sa.Column('club_reg', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    op.add_column('fuel_logs', sa.Column('receipt_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_fuel_logs_receipt', 'fuel_logs', 'receipts', ['receipt_id'], ['id'])

    op.add_column('diagnostics', sa.Column('status', sa.String(20), nullable=False, server_default='open'))
    op.add_column('diagnostics', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'logbook_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vehicle_id', sa.String(36), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('start_odometer_km', sa.Integer(), nullable=True),
        sa.Column('end_odometer_km', sa.Integer(), nullable=True),
        sa.Column('distance_km', sa.Float(), nullable=True),
        sa.Column('purpose', sa.String(12), nullable=False, server_default='private'),
        sa.Column('reason', sa.String(500), nullable=True),
        sa.Column('start_location', sa.String(255), nullable=True),
        sa.Column('end_location', sa.String(255), nullable=True),
        sa.Column('start_lat', sa.Float(), nullable=True),
        sa.Column('start_lng', sa.Float(), nullable=True),
        sa.Column('end_lat', sa.Float(), nullable=True),
        sa.Column('end_lng', sa.Float(), nullable=True),
        sa.Column('start_photo_key', sa.String(500), nullable=True),
        sa.Column('end_photo_key', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='in_progress'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_logbook_entries_vehicle_id', 'logbook_entries', ['vehicle_id'])
    op.create_index('ix_logbook_entries_started_at', 'logbook_entries', ['started_at'])

    op.create_table(
        'obd_codes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('vehicle_id', sa.String(36), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('code', sa.String(16), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='obd'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_obd_codes_vehicle_id', 'obd_codes', ['vehicle_id'])
    op.create_index('ix_obd_codes_code', 'obd_codes', ['code'])


def downgrade() -> None:
    op.drop_index('ix_obd_codes_code', table_name='obd_codes')
    op.drop_index('ix_obd_codes_vehicle_id', table_name='obd_codes')
    op.drop_table('obd_codes')
    op.drop_index('ix_logbook_entries_started_at', table_name='logbook_entries')
    op.drop_index('ix_logbook_entries_vehicle_id', table_name='logbook_entries')
    op.drop_table('logbook_entries')

    op.drop_column('diagnostics', 'resolved_at')
    op.drop_column('diagnostics', 'status')

    op.drop_constraint('fk_fuel_logs_receipt', 'fuel_logs', type_='foreignkey')
    op.drop_column('fuel_logs', 'receipt_id')

    op.drop_column('vehicles', 'club_reg')

    op.drop_column('users', 'obd_auto_connect')
    op.drop_column('users', 'obd_enabled')
    op.drop_column('users', 'free_account')
