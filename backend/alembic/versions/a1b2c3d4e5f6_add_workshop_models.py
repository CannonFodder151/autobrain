"""add workshops + workshop_users (multi-tenant shop scaffolding)

AUT-3705: Workshop tenant model (name, slug, email, address, subscription
tier) and WorkshopUser membership (role, MFA, token versioning) for the
AutoBrain Shop. See AUT-3684.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut3705_workshop_models"
down_revision: Union[str, None] = "z2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _has_table("workshops"):
        op.create_table(
            "workshops",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("slug", sa.String(80), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column(
                "subscription_tier",
                sa.String(20),
                nullable=False,
                server_default="starter",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_workshops_slug", "workshops", ["slug"], unique=True)

    if not _has_table("workshop_users"):
        op.create_table(
            "workshop_users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "workshop_id",
                sa.String(36),
                sa.ForeignKey("workshops.id"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "role",
                sa.String(20),
                nullable=False,
                server_default="tech",
            ),
            sa.Column("mfa_secret", sa.String(64), nullable=True),
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_workshop_users_workshop_id", "workshop_users", ["workshop_id"])
        op.create_index("ix_workshop_users_user_id", "workshop_users", ["user_id"])


def downgrade() -> None:
    if _has_table("workshop_users"):
        op.drop_table("workshop_users")
    if _has_table("workshops"):
        op.drop_table("workshops")