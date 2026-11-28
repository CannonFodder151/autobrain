"""merge_aut857_and_aut397

Revision ID: 6b8b6323deea
Revises: aut397, aut857_performance_indexes
Create Date: 2026-11-27 00:53:56.377636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6b8b6323deea'
down_revision: Union[str, None] = ('aut397', 'aut857_performance_indexes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
