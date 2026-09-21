"""add engineers + engineer_reviews tables (AUT-3661)

Engineer marketplace: certified mechanics/specialists with geospatial search
support. Engineers have specialty, rating, price, and availability fields.
Reviews update aggregate rating via _recalculate_rating().
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a3661engineers"
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
    if not _has_table("engineers"):
        op.create_table(
            "engineers",
            sa.Column("id", sa.String(36), primary_key=True),
            # Identity
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("phone", sa.String(32), nullable=True),
            # Location (geospatial search)
            sa.Column("lat", sa.Float, nullable=True),
            sa.Column("lon", sa.Float, nullable=True),
            sa.Column("postcode", sa.String(16), nullable=True),
            sa.Column("address", sa.String(512), nullable=True),
            # Professional details
            sa.Column("specialties", JSONB, nullable=False, server_default="[]"),
            sa.Column("certifications", JSONB, nullable=False, server_default="[]"),
            sa.Column("years_experience", sa.Integer, nullable=True),
            # Marketplace metrics
            sa.Column("rating", sa.Float, nullable=False, server_default="0"),
            sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("price_per_hour", sa.Float, nullable=True),
            sa.Column("price_per_job_min", sa.Float, nullable=True),
            sa.Column("price_per_job_max", sa.Float, nullable=True),
            # Availability
            sa.Column("availability", JSONB, nullable=False, server_default="[]"),
            # Status
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("verification_status", sa.String(20), nullable=False, server_default="pending"),
            # Embedding for semantic search
            sa.Column("embedding", sa.Text, nullable=True),
            # Timestamps
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
    if _has_table("engineer_reviews"):
        op.drop_table("engineer_reviews")
    if _has_table("engineers"):
        op.drop_table("engineers")