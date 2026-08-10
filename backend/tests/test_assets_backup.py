"""Self-check for MinIO assets backup/restore (no external services).

Run:  cd backend && python3 -m pytest tests/test_assets_backup.py -q
Uses a fake S3 client and app.services.assets pure tar logic; only needs the
few required settings env vars to import app.core.config.
"""

import io
import os
import tarfile
from datetime import datetime, timezone

os.environ.setdefault("POSTGRES_USER", "autobrain")
os.environ.setdefault("POSTGRES_PASSWORD", "autobrain")
os.environ.setdefault("MINIO_SECRET_KEY", "autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.assets import export_assets, restore_assets, validate_assets  # noqa: E402
from app.core.config import settings  # noqa: E402


class _Obj:
    def __init__(self, name, data):
        self.object_name = name
        self.data = data
        self.last_modified = datetime(2026, 8, 1, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeClient:
    def __init__(self):
        self.store = {}

    def seed(self, name, data):
        self.store[name] = data

    def list_objects(self, bucket):
        return iter(_Obj(n, d) for n, d in self.store.items())

    def get_object(self, bucket, name):
        return _Resp(self.store[name])

    def put_object(self, bucket, name, data, length, **kw):
        self.store[name] = data.read() if hasattr(data, "read") else data

    def remove_object(self, bucket, name):
        self.store.pop(name, None)


def test_export_validate_restore_roundtrip():
    client = FakeClient()
    client.seed("vehicles/v1/photo.jpg", b"\xff\xd8\xff photo")
    client.seed("receipts/abc.pdf", b"%PDF-1.4 receipt")

    archive = export_assets(client)
    assert archive[:2] == b"\x1f\x8b"  # gzip magic

    names = validate_assets(archive)
    assert sorted(names) == ["receipts/abc.pdf", "vehicles/v1/photo.jpg"]

    # wipe then restore
    client.store.clear()
    count = restore_assets(client, archive)
    assert count == 2
    assert client.store["vehicles/v1/photo.jpg"] == b"\xff\xd8\xff photo"
    assert client.store["receipts/abc.pdf"] == b"%PDF-1.4 receipt"

    # empty archive
    try:
        restore_assets(client, b"")
        raise AssertionError("empty archive accepted")
    except ValueError:
        pass

    # corrupt archive
    try:
        validate_assets(b"not a tar.gz at all")
        raise AssertionError("corrupt archive accepted")
    except ValueError:
        pass

    print("ok: assets export/validate/restore round-trip")


def test_archive_members_valid():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../../etc/passwd")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"abc"))
    try:
        validate_assets(buf.getvalue())
        raise AssertionError("path-traversal member accepted")
    except ValueError:
        pass
    print("ok: unsafe member rejected")
