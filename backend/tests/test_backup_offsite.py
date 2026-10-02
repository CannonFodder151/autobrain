"""Off-site backup push contract (AUT-5136).

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

import asyncio  # noqa: E402

import httpx  # noqa: E402

from app.core.logging import setup_logging  # noqa: E402
from app.services import backup_offsite  # noqa: E402

setup_logging()  # backup_offsite logs with structlog kwargs; stdlib logger rejects them


def test_backend_no_longer_owns_offsite_retention():
    """The backend must not prune the off-site store.

    AUT-5136: a second, age-derived retention engine ran over the same listing
    autobrain-backup already prunes per tier directory (engine.py::_prune),
    deleting 29 of 66 in-policy snapshots. The helpers are gone with it —
    `monthly` never existed as a tier on the service side either.
    """
    for gone in (
        "_apply_tiered_retention",
        "_list_existing_offsite",
        "_delete_offsite",
        "_tier_for_age",
        "_slot_key",
        "_OFFSITE_TIERS",
    ):
        assert not hasattr(backup_offsite, gone), f"{gone} must be removed — retention is owned by autobrain-backup"


def test_hourly_push_deletes_nothing_on_an_in_policy_store(monkeypatch):
    """Acceptance repro (AUT-5136): 24 hourly + 30 daily + 12 weekly.

    That listing is fully in policy for autobrain-backup's defaults
    (retention.hourly=24 / daily=30 / weekly=12), so a backend push must issue
    exactly one ingest POST and zero deletes. Pre-fix this path deleted 29/66.
    """
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings
    from app.db import session as session_mod

    now = datetime.now(timezone.utc)
    listing = [{"name": f"h{i}", "mtime": (now - timedelta(hours=i)).isoformat()} for i in range(24)]
    listing += [{"name": f"d{i}", "mtime": (now - timedelta(days=i)).isoformat()} for i in range(30)]
    listing += [{"name": f"w{i}", "mtime": (now - timedelta(weeks=i)).isoformat()} for i in range(12)]
    assert len(listing) == 66

    calls: list[tuple[str, str]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/api/backups"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "hourly": [{"name": b["name"], "mtime": b["mtime"], "size": 1} for b in listing[:24]],
                    "daily": [{"name": b["name"], "mtime": b["mtime"], "size": 1} for b in listing[24:54]],
                    "weekly": [{"name": b["name"], "mtime": b["mtime"], "size": 1} for b in listing[54:]],
                },
            )
        return httpx.Response(200, request=request, json={"ok": True})

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kw):
            return _handler(httpx.Request("GET", str(url)))

        async def post(self, url, **kw):
            return _handler(httpx.Request("POST", str(url)))

        async def delete(self, url, **kw):
            return _handler(httpx.Request("DELETE", str(url)))

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    async def _fake_serialize(db):
        return {"data": {"cars": []}}

    monkeypatch.setattr(backup_offsite.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(backup_offsite, "serialize_all", _fake_serialize)
    monkeypatch.setattr(session_mod, "SessionLocal", _FakeSession)
    monkeypatch.setattr(settings, "BACKUP_OFFSITE_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_OFFSITE_URL", "http://autobrain-backup:8080")
    monkeypatch.setattr(settings, "BACKUP_OFFSITE_INSTANCE", "hosted")

    asyncio.run(backup_offsite.run_backup_offsite())

    assert [c for c in calls if c[0] == "DELETE"] == [], "backend must never delete off-site backups"
    assert [c for c in calls if c[0] == "POST"] == [("POST", "/api/backup/ingest")]


def test_hourly_push_skips_when_disabled(monkeypatch):
    """BACKUP_OFFSITE_ENABLED guard survives the removal (AUT-5136)."""
    from app.core.config import settings

    calls: list[tuple[str, str]] = []

    class _BoomClient:
        def __init__(self, *a, **kw):
            raise AssertionError("no HTTP when disabled")

    monkeypatch.setattr(backup_offsite.httpx, "AsyncClient", _BoomClient)
    monkeypatch.setattr(settings, "BACKUP_OFFSITE_ENABLED", False)

    asyncio.run(backup_offsite.run_backup_offsite())
    assert calls == []