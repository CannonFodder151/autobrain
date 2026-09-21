"""initial_shop_schema

Revision ID: 2e9255029bfd
Revises: 
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2e9255029bfd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subscription tiers enum
    subscription_tier_enum = sa.Enum('starter', 'professional', 'enterprise', name='subscriptiontier')
    subscription_tier_enum.create(op.get_bind(), checkfirst=True)

    # Workshop roles enum
    workshop_role_enum = sa.Enum('owner', 'manager', 'tech', 'admin', name='workshoprole')
    workshop_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table('workshops',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('postcode', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=False, server_default='AU'),
        sa.Column('abn', sa.String(length=20), nullable=True),
        sa.Column('subscription_tier', sa.String(length=32), nullable=False, server_default='starter'),
        sa.Column('subscription_status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('stripe_customer_id', sa.String(length=64), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True),
        sa.Column('subscription_current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('max_vehicles', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('ai_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workshops_slug'), 'workshops', ['slug'], unique=True)
    op.create_index(op.f('ix_workshops_abn'), 'workshops', ['abn'], unique=False)
    op.create_index(op.f('ix_workshops_stripe_customer_id'), 'workshops', ['stripe_customer_id'], unique=False)

    op.create_table('workshop_users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('workshop_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='tech'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workshop_id'], ['workshops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workshop_id', 'email', name='uq_workshop_user_email')
    )
    op.create_index(op.f('ix_workshop_users_workshop_id'), 'workshop_users', ['workshop_id'], unique=False)
    op.create_index(op.f('ix_workshop_users_email'), 'workshop_users', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workshop_users_email'), table_name='workshop_users')
    op.drop_index(op.f('ix_workshop_users_workshop_id'), table_name='workshop_users')
    op.drop_table('workshop_users')
    op.drop_index(op.f('ix_workshops_stripe_customer_id'), table_name='workshops')
    op.drop_index(op.f('ix_workshops_abn'), table_name='workshops')
    op.drop_index(op.f('ix_workshops_slug'), table_name='workshops')
    op.drop_table('workshops')

    sa.Enum(name='workshoprole').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='subscriptiontier').drop(op.get_bind(), checkfirst=True)