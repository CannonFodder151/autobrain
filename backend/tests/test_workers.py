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

    fake_db = FakeDB()
    bucket = FakeBucket()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: fake_db)

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
