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
import logging  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.logging import setup_logging  # noqa: E402
from app.services import backup_offsite  # noqa: E402

setup_logging()
# AUT-5433: pytest's logging plugin attaches a root handler before collection,
# so setup_logging()'s logging.basicConfig() is a no-op and the root level
# stays WARNING — logger.info() then short-circuits before _log() ever runs.
# Force INFO so the structlog-kwarg call path below is genuinely exercised.
logging.getLogger().setLevel(logging.INFO)


def test_logger_accepts_structlog_kwargs():
    """AUT-5433 regression: the hourly task crashed every single run.

    `app.workers.tasks.backup_offsite_hourly` died with
    `TypeError: Logger._log() got an unexpected keyword argument 'reason'`
    because the module used a stdlib `logging.getLogger` while every call site
    passes structlog-style kwargs. Affected the disabled-guard paths (line 52/55)
    and the success/failure paths, i.e. all of them.
    """
    backup_offsite.logger.info("offsite_backup_skipped", reason="BACKUP_OFFSITE_ENABLED is False")
    backup_offsite.logger.error("offsite_backup_skipped", reason="BACKUP_OFFSITE_URL not configured")
    backup_offsite.logger.info("offsite_push_ok", filename="f.json", status=200)
    backup_offsite.logger.error("offsite_push_failed", filename="f.json", error="boom")
    backup_offsite.logger.info(
        "offsite_backup_done",
        filename="f.json",
        size=1,
        tables=1,
        pushed=True,
        duration_seconds=0.1,
    )


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
    assert [c for c in calls if c[0] == "POST"] == [("POST", "/ingest")]


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


def test_hourly_task_actually_awaits_the_push(monkeypatch):
    """AUT-5092: the task called the coroutine without awaiting it.

    Celery then reported success in ~1ms and nothing was ever pushed. Assert
    the coroutine actually runs to completion.
    """
    tasks = pytest.importorskip("app.workers.tasks")

    ran: list[str] = []

    async def _fake_run() -> None:
        ran.append("done")

    monkeypatch.setattr(backup_offsite, "run_backup_offsite", _fake_run)
    tasks.backup_offsite_hourly()
    assert ran == ["done"]


def test_push_uses_the_gui_ingest_path(monkeypatch):
    """AUT-5092: the GUI serves POST /ingest, not /api/backup/ingest (404)."""
    seen: dict = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, params=None, headers=None, content=None):
            seen.update(url=url, params=params, headers=headers)
            return _Resp()

    monkeypatch.setattr(backup_offsite.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(backup_offsite.settings, "BACKUP_OFFSITE_URL", "http://backup:8080")
    monkeypatch.setattr(backup_offsite.settings, "BACKUP_OFFSITE_INSTANCE", "hosted")
    monkeypatch.setattr(backup_offsite.settings, "BACKUP_OFFSITE_INGEST_KEY", "k")

    assert asyncio.run(backup_offsite._push_offsite(b"{}", "snap.json")) is True
    assert seen["url"] == "http://backup:8080/ingest"
    assert seen["params"] == {"instance": "hosted"}
    assert seen["headers"]["X-Ingest-Key"] == "k"
