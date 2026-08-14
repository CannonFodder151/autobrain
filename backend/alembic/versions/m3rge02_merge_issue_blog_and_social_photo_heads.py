"""merge issue-blog and social-photo branches

The Issues Blog tables (u1v2w3x4y5z6, AUT-643) and the IAP + build-photo
chains (q7r8s9t0u1v2 -> q1r2s3t4u5v6, AUT-617/AUT-675) both fork at
p6q7r8s9t0u1, leaving two alembic heads and breaking `alembic upgrade head`
in the boot command. This merge re-unifies them so the AUT-709 issue-photo
migration can chain off a single head. No schema change.

Revision ID: m3rge02
Revises: q1r2s3t4u5v6, u1v2w3x4y5z6
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge02"
down_revision: Union[str, Sequence[str], None] = ("q1r2s3t4u5v6", "u1v2w3x4y5z6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
