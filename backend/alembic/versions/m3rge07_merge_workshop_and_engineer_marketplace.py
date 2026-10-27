"""merge workshop-models, engineer-marketplace and passkey-credentials heads

Workshop scaffolding (aut3705) forks off the devices branch, leaving an
extra alembic head. This merge re-unifies it with the existing single head so
`alembic upgrade head` applies all branches. No schema change.

Revision ID: m3rge07
Revises: aut3705_workshop_models, a3661engineers, aut3447_passkey_credentials
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge07"
down_revision: Union[str, Sequence[str], None] = (
    "aut3705_workshop_models",
    "a3661engineers",
    "aut3447_passkey_credentials",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
