"""merge engineers marketplace + passkey credentials heads (AUT-4259)

a3661engineers (engineers + engineer_reviews tables) and aut3447_passkey_credentials
(passkey_credentials table) are both heads. This merge re-unifies them so
``alembic upgrade head`` keeps a single resolution path (AUT-702 single-head guard).
No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge07"
down_revision: Union[str, Sequence[str], None] = (
    "a3661engineers",
    "aut3447_passkey_credentials",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass