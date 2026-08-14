"""merge social-photo-position and issue-blog branches

The add_social_photo_position chain (q7r8s9t0u1v2 → q1r2s3t4u5v6, AUT-675)
and the add_issue_blog_tables chain (p6q7r8s9t0u1 → u1v2w3x4y5z6, AUT-649/627)
fork at p6q7r8s9t0u1/q7r8s9t0u1v2, leaving two alembic heads and breaking
`alembic upgrade head` in the boot command. This merge re-unifies them so
both branches apply regardless of which one a given database was stamped at
(the live demo/default/hosted DBs were already stamped at both heads by
AUT-682, so this must apply as a clean no-op there). No schema change.

AUT-510 pattern: no-op upgrade body.

Revision ID: m3rge02
Revises: q1r2s3t4u5v6, u1v2w3x4y5z6
Create Date: 2026-08-14 13:14:02.045429

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'm3rge02'
down_revision: Union[str, Sequence[str], None] = ('q1r2s3t4u5v6', 'u1v2w3x4y5z6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
