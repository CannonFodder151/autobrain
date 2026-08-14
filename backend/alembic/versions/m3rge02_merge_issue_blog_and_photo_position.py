"""merge issue-blog and social-photo-position branches

The Issues Blog chain (u1v2w3x4y5z6, AUT-627, down_revision p6q7r8s9t0u1)
and the photo-position chain (q1r2s3t4u5v6, AUT-675, down_revision
q7r8s9t0u1v2) fork at p6q7r8s9t0u1, leaving two alembic heads and breaking
`alembic upgrade head` in the boot command (bootstrap falls back to
create_all, so later migration columns never apply). This merge re-unifies
them into a linear chain so both branches apply on every database. No schema
change.

Revision ID: m3rge02
Revises: u1v2w3x4y5z6, q1r2s3t4u5v6
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union


revision: str = "m3rge02"
down_revision: Union[str, Sequence[str], None] = ("u1v2w3x4y5z6", "q1r2s3t4u5v6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
