"""Add APNS token to notification_preferences (AUT-466b).

Adds apns_token column for Apple Push Notification service support
alongside existing FCM token. The push dispatcher auto-detects token
format (FCM vs APNS) and routes accordingly.

Also adds deep_link support to fuel price alert notifications via
the notification payload data field.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut466b_apns_token"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("notification_preferences", "apns_token"):
        op.add_column(
            "notification_preferences",
            sa.Column("apns_token", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("notification_preferences", "apns_token"):
        op.drop_column("notification_preferences", "apns_token")