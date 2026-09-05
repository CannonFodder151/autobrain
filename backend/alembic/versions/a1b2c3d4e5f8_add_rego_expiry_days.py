"""add rego_expiry_days to notification_preferences + vehicle rego cache (AUT-2416)

Premium per-user threshold: alert when a vehicle's rego expiry date is within
this many days. 0 = disabled. Mirrors the existing service_due_days pattern.

Also adds the per-vehicle rego cache columns (status / expiry_date / checked_at)
that the daily rego-refresh job (AUT-2414) and the per-lookup rego-lookup
endpoint both write into. The frontend badge (AUT-2415) and the expiry
notification (AUT-2416) both read these. Keeps the schema bump atomic with
the dependent changes so deploys never read missing columns.

Merge revision: both ``z2a3b4c5d6e7`` (current main head) and
``aut1859_fuel_price_alerts`` (the AUT-1859 fuel-price-alerts branch that
isn't yet merged into main) descend from this migration so ``alembic
upgrade head`` keeps a single resolution path (AUT-702 single-head guard).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = (
    "z2a3b4c5d6e7",
    "aut1859_fuel_price_alerts",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column(
            "rego_expiry_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column("rego_status", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "vehicles",
        sa.Column("rego_expiry_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_vehicles_rego_expiry_date", "vehicles", ["rego_expiry_date"], unique=False
    )
    op.add_column(
        "vehicles",
        sa.Column("rego_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehicles", "rego_checked_at")
    op.drop_index("ix_vehicles_rego_expiry_date", table_name="vehicles")
    op.drop_column("vehicles", "rego_expiry_date")
    op.drop_column("vehicles", "rego_status")
    op.drop_column("notification_preferences", "rego_expiry_days")
