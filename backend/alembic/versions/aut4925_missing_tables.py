"""Create tables a stamped DB skipped: passkey_credentials, engineers, engineer_reviews (AUT-4925)

`alembic_version` on hosted (EP5) read `aut3447_passkey_credentials`, but
`passkey_credentials`, `engineers` and `engineer_reviews` were absent — the
version was stamped past DDL that never ran. Head migration `f7e8d9c0b1a2`
then failed on the missing table, so every boot fell back to `create_all` and
the version never advanced. This repair creates whatever is missing and is a
no-op on DBs that already have the tables.

Revision ID: aut4925_missing_tables
Revises: f7e8d9c0b1a2
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "aut4925_missing_tables"
down_revision: Union[str, Sequence[str], None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("passkey_credentials"):
        op.create_table(
            "passkey_credentials",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("credential_id", sa.String(512), nullable=False),
            sa.Column("public_key", sa.Text(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("label", sa.String(120), nullable=False, server_default=""),
            sa.Column("device_type", sa.String(20), nullable=False, server_default="unknown"),
            sa.Column("transports", sa.String(100), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"])
        op.create_index("ix_passkey_credentials_credential_id", "passkey_credentials", ["credential_id"])

    if not _has_table("engineers"):
        op.create_table(
            "engineers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("phone", sa.String(32), nullable=True),
            sa.Column("lat", sa.Float, nullable=True),
            sa.Column("lon", sa.Float, nullable=True),
            sa.Column("postcode", sa.String(16), nullable=True),
            sa.Column("address", sa.String(512), nullable=True),
            sa.Column("specialties", JSONB, nullable=False, server_default="[]"),
            sa.Column("certifications", JSONB, nullable=False, server_default="[]"),
            sa.Column("years_experience", sa.Integer, nullable=True),
            sa.Column("rating", sa.Float, nullable=False, server_default="0"),
            sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("price_per_hour", sa.Float, nullable=True),
            sa.Column("price_per_job_min", sa.Float, nullable=True),
            sa.Column("price_per_job_max", sa.Float, nullable=True),
            sa.Column("availability", JSONB, nullable=False, server_default="[]"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("verification_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("embedding", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_engineers_email", "engineers", ["email"])
        op.create_index("ix_engineers_postcode", "engineers", ["postcode"])
        op.create_index("ix_engineers_display_name", "engineers", ["display_name"])
        op.create_index("ix_engineers_rating", "engineers", ["rating"])
        op.create_index("ix_engineers_price_per_hour", "engineers", ["price_per_hour"])
        op.create_index("ix_engineers_price_per_job_min", "engineers", ["price_per_job_min"])
        op.create_index("ix_engineers_price_per_job_max", "engineers", ["price_per_job_max"])
        op.create_index("ix_engineers_active_rating", "engineers", ["is_active", "rating"])
        op.create_index("ix_engineers_active_price", "engineers", ["is_active", "price_per_hour"])
        op.create_index("ix_engineers_active_verified", "engineers", ["is_active", "is_verified"])
        op.create_index("ix_engineers_postcode_active", "engineers", ["postcode", "is_active"])

    if not _has_table("engineer_reviews"):
        op.create_table(
            "engineer_reviews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("engineer_id", sa.String(36), sa.ForeignKey("engineers.id"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("rating", sa.Integer, nullable=False),
            sa.Column("title", sa.String(200), nullable=True),
            sa.Column("body", sa.Text, nullable=True),
            sa.Column("service_type", sa.String(60), nullable=True),
            sa.Column("cost", sa.Float, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            # a3661engineers omitted this; the ORM model has it, so a fresh
            # table must too or every review insert fails on a missing column.
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_engineer_reviews_engineer_id", "engineer_reviews", ["engineer_id"])
        op.create_index("ix_engineer_reviews_user_id", "engineer_reviews", ["user_id"])
        op.create_index("ix_engineer_reviews_vehicle_id", "engineer_reviews", ["vehicle_id"])
        op.create_index(
            "ix_engineer_reviews_engineer_created",
            "engineer_reviews",
            ["engineer_id", "created_at"],
        )


def downgrade() -> None:
    for name in ("engineer_reviews", "engineers", "passkey_credentials"):
        if _has_table(name):
            op.drop_table(name)