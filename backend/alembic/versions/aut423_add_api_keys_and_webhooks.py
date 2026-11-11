"""add api_keys + webhooks for public developer API (AUT-423)

Adds:
- api_keys: per-user API keys with scopes and rate limits
- webhooks: per-user webhook registrations with event subscriptions
- webhook_deliveries: delivery tracking with retry/backoff

Keys are stored as sha256 digests with prefix index for lookup.
Webhooks are signed with HMAC-SHA256 for receiver verification.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut423_add_api_keys_and_webhooks"
down_revision: Union[str, None] = "m3rge08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def upgrade() -> None:
    # api_keys
    if not _has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("api_key_prefix", sa.String(14), nullable=False),
            sa.Column("api_key_hash", sa.String(64), nullable=False),
            sa.Column("scopes", sa.Text, server_default="[]", nullable=False),
            sa.Column("rate_limit", sa.Integer, nullable=True),
            sa.Column("rate_window_seconds", sa.Integer, nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
        op.create_index("ix_api_keys_api_key_prefix", "api_keys", ["api_key_prefix"])

    # webhooks
    if not _has_table("webhooks"):
        op.create_table(
            "webhooks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("url", sa.String(512), nullable=False),
            sa.Column("events", sa.Text, server_default="[]", nullable=False),
            sa.Column("secret", sa.String(64), nullable=False),
            sa.Column("secret_prefix", sa.String(8), nullable=False),
            sa.Column("status", sa.String(16), server_default="active", nullable=False),
            sa.Column("max_retries", sa.Integer, server_default="5", nullable=False),
            sa.Column("consecutive_failures", sa.Integer, server_default="0", nullable=False),
            sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failure_reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])
        op.create_index("ix_webhooks_secret_prefix", "webhooks", ["secret_prefix"])

    # webhook_deliveries
    if not _has_table("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("webhook_id", sa.String(36), sa.ForeignKey("webhooks.id"), nullable=False),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("payload", sa.Text, nullable=False),
            sa.Column("http_status", sa.Integer, nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
        op.create_index("ix_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"])
        op.create_index("ix_webhook_deliveries_next_retry_at", "webhook_deliveries", ["next_retry_at"])


def downgrade() -> None:
    if _has_table("webhook_deliveries"):
        op.drop_table("webhook_deliveries")
    if _has_table("webhooks"):
        op.drop_table("webhooks")
    if _has_table("api_keys"):
        op.drop_table("api_keys")