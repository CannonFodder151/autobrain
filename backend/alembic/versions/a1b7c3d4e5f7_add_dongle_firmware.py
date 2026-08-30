"""add dongle firmware manifest + installed telemetry (AUT-1673)

Dongle (esp32-diy BLE+WiFi) OTA support:

- ``dongle_firmware`` — one row per released firmware per model. The blob
  itself lives in MinIO (key ``dongle_firmware/<id>.bin``); the row stores
  only the manifest that the app uses to fetch a short-lived signed URL and
  decide whether an update is available.

- ``dongle_installed_firmware`` — one row per device, populated by the
  dongle's POST /dongle/firmware/report call (device-authenticated). Lets the
  app render "Update available" + serial number without re-reading BLE on
  every page load.

DDL ops are guarded so DBs where the tables were created by bootstrap's
create_all fallback apply cleanly as no-ops (AUT-510 pattern).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "a1b7c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "o5n6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _online() and not _has(bind, "dongle_firmware"):
        op.create_table(
            "dongle_firmware",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("model", sa.String(length=64), nullable=False, index=True),
            sa.Column("version", sa.String(length=32), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("blob_key", sa.String(length=256), nullable=False),
            sa.Column("release_notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("model", "version", name="uq_dongle_firmware_model_version"),
        )
    if _online() and not _has(bind, "dongle_installed_firmware"):
        op.create_table(
            "dongle_installed_firmware",
            sa.Column(
                "device_id",
                sa.String(length=36),
                sa.ForeignKey("devices.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("model", sa.String(length=64), nullable=False),
            sa.Column("firmware_version", sa.String(length=32), nullable=False),
            sa.Column("serial_number", sa.String(length=64), nullable=False),
            sa.Column(
                "last_reported_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _online() and _has(bind, "dongle_installed_firmware"):
        op.drop_table("dongle_installed_firmware")
    if _online() and _has(bind, "dongle_firmware"):
        op.drop_table("dongle_firmware")
