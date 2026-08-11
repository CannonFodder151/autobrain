"""add_user_token_version_and_refresh_denylist

Revision ID: h2j3k4l5m6n7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h2j3k4l5m6n7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bump token_version to revoke ALL outstanding access + refresh tokens
    # (logout, password change). Existing tokens carry no `ver` claim, which
    # decodes as 0 == the default, so the rollout is backwards compatible.
    op.add_column(
        'users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0')
    )
    # Refresh-rotation denylist: each consumed/rotated refresh token's jti is
    # recorded here so a replayed (stolen) token is rejected.
    op.create_table(
        'revoked_refresh_tokens',
        sa.Column('jti', sa.String(length=32), primary_key=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_revoked_refresh_tokens_expires_at', 'revoked_refresh_tokens', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_revoked_refresh_tokens_expires_at', table_name='revoked_refresh_tokens')
    op.drop_table('revoked_refresh_tokens')
    op.drop_column('users', 'token_version')
