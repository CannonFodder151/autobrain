"""Create vehicle_health_scores table (AUT-3359).

Adds per-vehicle health score storage with one row per vehicle (score 0-100,
deterministic rule breakdown, last computed timestamp).  The table uses a
unique FK to vehicles so there is exactly one score row per vehicle.

Revision ID: aut3359_vehicle_health_score
Revises: z2a3b4c5d6e7
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut3359_vehicle_health_score"
down_revision: Union[str, Sequence[str], None] = "z2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_health_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), unique=True, index=True),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_computed", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("computed_by", sa.String(64), default="deterministic"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("vehicle_health_scores")