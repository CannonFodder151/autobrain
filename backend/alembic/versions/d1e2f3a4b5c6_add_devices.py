"""add devices (dongle) + logbook device attribution

AUT-918: dongle (devices) table for WiFi trip auto-upload. Each device is a
per-user hardware token authenticating via X-Device-API-Key (sha256 hash
stored). logbook_entries gains device_id + device_trip_id with a unique pair
so unattended uploads dedupe idempotently on WiFi retries.

AUT-510 pattern: DDL ops are guarded so DBs where the tables were created by
bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "x1y2z3a4b5c6"
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
    if not _has_table("devices"):
        op.create_table(
            "devices",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("api_key_prefix", sa.String(10), nullable=False),
            sa.Column("api_key_hash", sa.String(64), nullable=False),
            sa.Column("vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_devices_user_id", "devices", ["user_id"])
        op.create_index("ix_devices_api_key_prefix", "devices", ["api_key_prefix"])
    # logbook_entries column adds are idempotent on the unique constraint name.
    bind = op.get_bind()
    if _online():
        columns = {c["name"] for c in sa.inspect(bind).get_columns("logbook_entries")}
        if "device_id" not in columns:
            op.add_column(
                "logbook_entries",
                sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=True),
            )
        if "device_trip_id" not in columns:
            op.add_column("logbook_entries", sa.Column("device_trip_id", sa.String(64), nullable=True))
        constraints = {c["name"] for c in sa.inspect(bind).get_unique_constraints("logbook_entries")}
        if "uq_logbook_device_trip" not in constraints:
            op.create_unique_constraint(
                "uq_logbook_device_trip", "logbook_entries", ["device_id", "device_trip_id"]
            )


def downgrade() -> None:
    if not _has_table("logbook_entries"):
        return
    bind = op.get_bind()
    if _online():
        constraints = {c["name"] for c in sa.inspect(bind).get_unique_constraints("logbook_entries")}
        if "uq_logbook_device_trip" in constraints:
            op.drop_constraint("uq_logbook_device_trip", "logbook_entries", type_="unique")
        if _has_table("devices"):
            # Drop the FK first so the devices table can go; the plain columns
            # stay (harmless nullable) to keep the downgrade simple.
            fks = {f["name"] for f in sa.inspect(bind).get_foreign_keys("logbook_entries")}
            fk = next((n for n in fks if n and "device" in n), None)
            if fk:
                op.drop_constraint(fk, "logbook_entries", type_="foreignkey")
    if _has_table("devices"):
        op.drop_table("devices")