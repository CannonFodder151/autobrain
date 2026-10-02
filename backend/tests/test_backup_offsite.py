"""Off-site backup retention tiers + slot keys (AUT-3827).

Run (sqlite, no Postgres needed):
    cd backend && python3 -m pytest tests/test_backup_offsite.py -q
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/autobrain-offsite-test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("POSTGRES_USER", "autobrain")
os.environ.setdefault("POSTGRES_PASSWORD", "autobrain")
os.environ.setdefault("POSTGRES_DB", "autobrain")
os.environ.setdefault("MINIO_ACCESS_KEY", "autobrain")
os.environ.setdefault("MINIO_SECRET_KEY", "autobrain")
os.environ.setdefault("MINIO_BUCKET", "autobrain-assets")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("AI_GATEWAY_API_KEY", "test-ai-key")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-0123456789-0123456789")
os.environ.setdefault("MARKET_DATA_URL", "")
os.environ.setdefault("MARKET_DATA_API_KEY", "")

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.services.backup_offsite import _slot_key, _tier_for_age  # noqa: E402


def test_tier_for_age_boundaries():
    assert _tier_for_age(0) == "hourly"
    assert _tier_for_age(23) == "hourly"
    assert _tier_for_age(24) == "daily"
    assert _tier_for_age(24 * 7 - 1) == "daily"
    assert _tier_for_age(24 * 7) == "weekly"
    assert _tier_for_age(24 * 28 - 1) == "weekly"
    assert _tier_for_age(24 * 28) == "monthly"
    # Beyond the monthly window the snapshot is prunable.
    assert _tier_for_age(24 * 28 * 6) is None


def test_slot_key_is_stable_per_tier_window():
    ts = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)
    assert _slot_key(ts, "hourly") == "20260115-09"
    assert _slot_key(ts, "daily") == "20260115"
    # Two snapshots in the same ISO week collapse to one weekly slot.
    assert _slot_key(ts, "weekly") == _slot_key(
        datetime(2026, 1, 18, 4, 0, tzinfo=timezone.utc), "weekly"
    )
    assert _slot_key(ts, "monthly") == "2026-01"


def test_monthly_tier_is_listed_from_offsite():
    """The off-site list must flatten every tier retention manages.

    Regression: `monthly` was missing from the flatten loop, so monthly
    snapshots were invisible to retention — never deduped, never pruned.
    """
    from app.services import backup_offsite

    assert "monthly" in backup_offsite._OFFSITE_TIERS


def test_retention_keeps_one_per_slot_and_prunes_expired(monkeypatch):
    """Two snapshots in the same slot → one kept; expired ones → deleted."""
    import asyncio

    from app.services import backup_offsite

    now = datetime.now(timezone.utc)
    kept = now.isoformat().replace("+00:00", "Z")
    dup = (now.replace(minute=0, second=0, microsecond=0)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(days=400)).isoformat().replace("+00:00", "Z")

    deleted: list[str] = []

    async def _fake_delete(name: str) -> bool:
        deleted.append(name)
        return True

    monkeypatch.setattr(backup_offsite, "_delete_offsite", _fake_delete)
    asyncio.run(
        backup_offsite._apply_tiered_retention(
            [
                {"file": "keep.json", "timestamp": kept},
                {"file": "dup.json", "timestamp": dup},
                {"file": "expired.json", "timestamp": old},
                {"file": "no-timestamp.json"},
            ]
        )
    )
    assert sorted(deleted) == ["dup.json", "expired.json"]