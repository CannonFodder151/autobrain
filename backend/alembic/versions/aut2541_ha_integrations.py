"""ha_integrations table (AUT-2541).

Per-user opaque token for Home Assistant to poll AutoBrain analytics and
service-interval data. Same storage shape as `devices`: prefix index +
sha256 digest only.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "aut2541_ha_integrations"
down_revision: Union[str, Sequence[str], None] = "m3rge05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ha_integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("label", sa.String(80), nullable=False, server_default="Home Assistant"),
        sa.Column("api_key_prefix", sa.String(10), nullable=False, index=True),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ha_integrations")
