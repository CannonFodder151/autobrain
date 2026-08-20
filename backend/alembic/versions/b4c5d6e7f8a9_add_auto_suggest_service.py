"""add auto_suggest_service + merge oil service type

AUT-1275:
- vehicles gains auto_suggest_service (bool) so the owner can opt each car
  into suggesting the next scheduled service whenever the odometer is updated.
- Existing legacy oil-change service records are folded into "scheduled"
  (oil/oil_change -> scheduled) to match the product decision that Oil Change
  is bundled as the Scheduled Service type.

DDL ops are guarded so DBs where the tables were created by bootstrap's
create_all fallback apply cleanly as no-ops (AUT-510 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "m3rge03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def upgrade() -> None:
    bind = op.get_bind()
    if _online():
        columns = {c["name"] for c in sa.inspect(bind).get_columns("vehicles")}
        if "auto_suggest_service" not in columns:
            op.add_column(
                "vehicles",
                sa.Column("auto_suggest_service", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        op.execute(
            "UPDATE service_records SET service_type = 'scheduled' "
            "WHERE service_type IN ('oil', 'oil_change')"
        )


def downgrade() -> None:
    if _online():
        bind = op.get_bind()
        columns = {c["name"] for c in sa.inspect(bind).get_columns("vehicles")}
        if "auto_suggest_service" in columns:
            op.drop_column("vehicles", "auto_suggest_service")
    # The oil->scheduled data fold is intentionally NOT reversed: once merged we
    # cannot tell which "scheduled" rows were originally oil change records.