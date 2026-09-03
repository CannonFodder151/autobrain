"""Worker task regression tests (mocked DB/manager, no live services)."""

import pytest  # noqa: F401

from app.workers import tasks


class FakeReceipt:
    id = "receipt-1"
    file_key = "k"
    content_type = "text/plain"
    original_name = "r.png"
    vehicle_id = "vehicle-1"
    ocr_status = None
    vendor = total = tax = currency = invoice_date = extracted = None


class FakeVehicle:
    id = "vehicle-1"
    user_id = "user-9"


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, pk):
        if model is tasks.Vehicle:
            return FakeVehicle()
        if model is tasks.Receipt:
            return FakeReceipt()
        return None

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    def add(self, obj):
        pass


class FakeManager:
    def __init__(self):
        self.sent = []

    async def send_to_user(self, user_id, event, payload):
        self.sent.append((user_id, event, payload))


def test_receipt_push_targets_vehicle_owner(monkeypatch) -> None:
    fake_db = FakeDB()
    fake_mgr = FakeManager()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(tasks, "manager", fake_mgr)
    async def fake_get(key):
        return b"x"

    monkeypatch.setattr(tasks, "get_object", fake_get)

    async def fake_extract(payload):
        return {"vendor": "V", "total": 1.0}

    monkeypatch.setattr(tasks, "extract_receipt", fake_extract)

    tasks.process_receipt("receipt-1")

    assert fake_mgr.sent, "expected a receipt.processed push"
    user_id, event, payload = fake_mgr.sent[0]
    assert user_id == "user-9", f"push sent to {user_id!r}, expected vehicle owner user-9"
    assert event == "receipt.processed"
    assert payload["receipt_id"] == "receipt-1"


class FakeBucket:
    def __init__(self):
        self.written = []
        self.removed = []

    def put_object(self, bucket, key, body, length, content_type):
        self.written.append((bucket, key, length, content_type))

    def list_objects(self, bucket, prefix=""):
        return []

    def remove_object(self, bucket, key):
        self.removed.append(key)


def test_scheduled_backup_stores_snapshot(monkeypatch) -> None:
    import app.core.storage as storage
    import app.services.backup as svc_backup
    from app.core.config import settings

    fake_db = FakeDB()
    bucket = FakeBucket()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(settings, "MINIO_BUCKET", "test-minio-bucket")
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "ak")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "sk")

    async def fake_serialize(db):
        assert db is fake_db
        return {"users": [], "vehicles": []}

    monkeypatch.setattr(svc_backup, "serialize_all", fake_serialize)
    monkeypatch.setattr(svc_backup, "dump_backup", lambda data: b'{"ok":true}')
    monkeypatch.setattr(storage, "get_minio", lambda: bucket)

    tasks.scheduled_backup()

    assert bucket.written, "expected a snapshot to be written to MinIO"
    bkt, key, length, ctype = bucket.written[0]
    assert bkt == "test-minio-bucket", f"bucket={bkt!r}"
    assert key.startswith("backups/autobrain-backup-"), key
    assert ctype == "application/json", ctype


def test_scheduled_backup_skips_on_missing_minio_credentials(monkeypatch, caplog) -> None:
    """AUT-2256: missing MINIO_* keys must skip-with-log, never Celery-FAIL.

    A bare worker (lib-load-secrets.sh never sourced, or secret file unmounted)
    must not turn every daily beat tick into a Celery FAIL with stack traces
    that hide the real config issue.
    """
    import logging

    from app.core.config import settings

    bucket = FakeBucket()
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "")
    monkeypatch.setattr(settings, "MINIO_BUCKET", "test-minio-bucket")
    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeDB())

    import app.core.storage as storage
    monkeypatch.setattr(storage, "get_minio", lambda: bucket)

    with caplog.at_level(logging.ERROR, logger="autobrain.workers"):
        tasks.scheduled_backup()

    assert bucket.written == [], "must not write without credentials"
    assert any(
        "minio_credentials_missing" in rec.message for rec in caplog.records
    ), f"expected minio_credentials_missing log, got: {[r.message for r in caplog.records]}"


def test_scheduled_backup_recovers_from_prune_error(monkeypatch) -> None:
    """AUT-2256: a prune failure must not fail the snapshot upload.

    Retention pruning is best-effort. The snapshot landed in MinIO; logging
    the prune error is the right outcome, not a Celery FAIL that loses the
    day's backup.
    """
    import app.core.storage as storage
    import app.services.backup as svc_backup
    from app.core.config import settings

    fake_db = FakeDB()
    bucket = FakeBucket()

    class FlakyPruneBucket(FakeBucket):
        def list_objects(self, bucket, prefix=""):
            raise RuntimeError("minio unreachable during prune")

    bucket = FlakyPruneBucket()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(settings, "MINIO_BUCKET", "test-minio-bucket")
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "ak")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "sk")

    async def fake_serialize(db):
        return {"users": [], "vehicles": []}

    monkeypatch.setattr(svc_backup, "serialize_all", fake_serialize)
    monkeypatch.setattr(svc_backup, "dump_backup", lambda data: b'{"ok":true}')
    monkeypatch.setattr(storage, "get_minio", lambda: bucket)

    tasks.scheduled_backup()

    assert bucket.written, "snapshot upload must succeed even when prune errors"


def test_run_recreates_wedged_persistent_loop(monkeypatch) -> None:
    """AUT-2256: a RuntimeError('Event loop is closed') from a prior task
    must recreate the loop on the next call instead of poisoning the worker.
    """
    closed_loop = tasks._loop
    # Pretend the persistent loop was killed by a previous task.
    if closed_loop is None or not closed_loop.is_closed():
        # Force-create one and immediately close it to simulate the wedge.
        import asyncio as _aio

        tmp = _aio.new_event_loop()
        tmp.close()
        tasks._loop = tmp

    import app.services.backup as svc_backup

    async def fake_serialize(db):
        return {}

    monkeypatch.setattr(svc_backup, "serialize_all", fake_serialize)
    monkeypatch.setattr(svc_backup, "dump_backup", lambda d: b"{}")

    class _Bucket(FakeBucket):
        pass

    import app.core.storage as storage
    monkeypatch.setattr(storage, "get_minio", lambda: _Bucket())
    monkeypatch.setattr(tasks, "SessionLocal", lambda: FakeDB())

    # Must not raise; _loop must be replaced with a fresh live one.
    tasks.scheduled_backup()
    assert tasks._loop is not None and not tasks._loop.is_closed(), (
        "persistent loop must be replaced when wedged"
    )
