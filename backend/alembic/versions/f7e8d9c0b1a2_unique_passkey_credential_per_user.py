"""Add unique constraint on passkey_credentials.credential_id per user.

Revision ID: f7e8d9c0b1a2
Revises: z2a3b4c5d6e7
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f7e8d9c0b1a2'
down_revision = 'm3rge07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint on (user_id, credential_id)
    op.create_unique_constraint(
        'uq_passkey_credential_user_credential',
        'passkey_credentials',
        ['user_id', 'credential_id']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_passkey_credential_user_credential',
        'passkey_credentials',
        type_='unique'
    )
