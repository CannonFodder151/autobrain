"""merge aut2541_ha_integrations + aut2706_device_vehicle_type heads (AUT-2714)

aut2541_ha_integrations (ha_integrations table) and aut2706_device_vehicle_type
(devices.vehicle_type column) are both heads descending from m3rge05. This merge
re-unifies them so ``alembic upgrade head`` keeps a single resolution path
(AUT-702 single-head guard). No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge06"
down_revision: Union[str, Sequence[str], None] = (
    "aut2541_ha_integrations",
    "aut2706_device_vehicle_type",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
