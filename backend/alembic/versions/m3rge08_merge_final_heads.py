"""merge all heads (AUT-380 follow-up, AUT-226)

Unifies the four script-tree heads:
  - a3661engineers (engineer marketplace)
  - aut3447_passkey_credentials (WebAuthn passkey auth)
  - aut5092_dev_veh_type (device vehicle_type repair)
  - g7h8i9j0k1l3 (pgvector remaining embeddings)

All four were merged straight into main, leaving multiple alembic heads and
breaking ``alembic upgrade head`` at bootstrap (fallback to ``create_all``).
This merge re-unifies them so the AUT-702 single-head guard passes.
No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge08"
down_revision: Union[str, Sequence[str], None] = (
    "a3661engineers",
    "aut3447_passkey_credentials",
    "aut5092_dev_veh_type",
    "g7h8i9j0k1l3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
