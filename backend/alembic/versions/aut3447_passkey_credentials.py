"""add passkey_credentials table (AUT-3447: WebAuthn passkey authentication)

Stores WebAuthn credential registrations for passwordless login.
Each row maps one authenticator to a user, holding the credential ID,
COSE public key, monotonic sign count, and device metadata.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut3447_passkey_credentials"
down_revision: Union[str, None] = "aut2705_phev_logbook_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(table: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return table in insp.get_table_names()


def upgrade() -> None:
    if _online() and _has_table("passkey_credentials"):
        return  # already present
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.String(512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("device_type", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("transports", sa.String(100), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"])
    op.create_index("ix_passkey_credentials_credential_id", "passkey_credentials", ["credential_id"])


def downgrade() -> None:
    if not _online() or not _has_table("passkey_credentials"):
        return
    op.drop_index("ix_passkey_credentials_credential_id", table_name="passkey_credentials")
    op.drop_index("ix_passkey_credentials_user_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
