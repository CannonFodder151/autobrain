"""merge social follow and device vehicle type heads

Revision ID: bd507a1c713f
Revises: a1b2c3d4e5f9, aut5092_dev_veh_type
Create Date: 2026-11-02 00:14:24.156009

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bd507a1c713f'
down_revision: Union[str, None] = ('a1b2c3d4e5f9', 'aut5092_dev_veh_type')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
