"""Add unique constraint on passkey_credentials.credential_id per user.

Skipped when the table is absent: DBs stamped past `aut3447_passkey_credentials`
without the DDL ever running (hosted, EP5) hard-failed here, which pushed every
boot into the `create_all` fallback and left the alembic version stuck forever.
`aut4925_missing_tables` creates the table.

Revision ID: f7e8d9c0b1a2
Revises: z2a3b4c5d6e7
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision = 'f7e8d9c0b1a2'
down_revision = 'm3rge07'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_constraint(name: str) -> bool:
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if not _has_table("passkey_credentials"):
        return False  # nothing to reflect; table created by aut4925_missing_tables
    insp = sa.inspect(bind)
    return any(c["name"] == name for c in insp.get_unique_constraints("passkey_credentials"))


def upgrade() -> None:
    if not _has_table("passkey_credentials"):
        return  # created by aut4925_missing_tables
    if _has_constraint("uq_passkey_credential_user_credential"):
        return
    op.create_unique_constraint(
        'uq_passkey_credential_user_credential',
        'passkey_credentials',
        ['user_id', 'credential_id']
    )


def downgrade() -> None:
    if not _has_table("passkey_credentials"):
        return
    if not _has_constraint("uq_passkey_credential_user_credential"):
        return
    op.drop_constraint(
        'uq_passkey_credential_user_credential',
        'passkey_credentials',
        type_='unique'
    )