"""MinIO object backup/restore (admin only).

Exports every object in the instance's MINIO_BUCKET as a gzipped tar archive
and restores an archive back into the bucket (wipe + re-upload). Used by the
off-box autobrain-backup service so image data survives alongside the DB
snapshot.

Pure functions over a duck-typed S3 client (list_objects/get_object/
put_object/remove_object) so the tar logic is testable without MinIO.
"""

import io
import tarfile

from app.core.config import settings


def export_assets(client) -> bytes:
    """Tar.gz every object in MINIO_BUCKET; returns the archive bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for obj in client.list_objects(settings.MINIO_BUCKET):
            if getattr(obj, "is_dir", False) or obj.object_name.endswith("/"):
                continue  # zero-byte directory marker object; not a file
            resp = client.get_object(settings.MINIO_BUCKET, obj.object_name)
            try:
                data = resp.read()
            finally:
                resp.close()
                resp.release_conn()
            info = tarfile.TarInfo(obj.object_name)
            info.size = len(data)
            info.mtime = int(obj.last_modified.timestamp()) if obj.last_modified else 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def validate_assets(raw: bytes) -> list[str]:
    """Return the member names if raw is a readable tar.gz; else raise ValueError."""
    if not raw:
        raise ValueError("Empty archive")
    names = []
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    raise ValueError("Archive contains a non-file entry")
                name = member.name
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError("Archive contains an unsafe member name")
                names.append(name)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ValueError(f"Invalid image archive: {exc}") from exc
    return names


def validate_assets_file(path: str) -> list[str]:
    """Return the member names of a tar.gz on disk without loading it into memory."""
    names = []
    try:
        with tarfile.open(name=path, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    raise ValueError("Archive contains a non-file entry")
                name = member.name
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError("Archive contains an unsafe member name")
                names.append(name)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ValueError(f"Invalid image archive: {exc}") from exc
    return names


def restore_assets(client, raw: bytes) -> int:
    """Wipe the bucket then upload every member of a validated archive."""
    members = validate_assets(raw)
    for obj in client.list_objects(settings.MINIO_BUCKET):
        client.remove_object(settings.MINIO_BUCKET, obj.object_name)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        for member in tar.getmembers():
            f = tar.extractfile(member)
            data = f.read() if f else b""
            client.put_object(
                settings.MINIO_BUCKET, member.name, io.BytesIO(data),
                length=len(data),
            )
    return len(members)


def restore_assets_file(client, path: str) -> int:
    """Wipe the bucket then upload every member of a validated archive on disk.

    Streams each member to MinIO without holding the whole archive in memory.
    """
    members = validate_assets_file(path)
    for obj in client.list_objects(settings.MINIO_BUCKET):
        client.remove_object(settings.MINIO_BUCKET, obj.object_name)
    with tarfile.open(name=path, mode="r:gz") as tar:
        for member in tar.getmembers():
            f = tar.extractfile(member)
            if f is None:
                continue
            client.put_object(
                settings.MINIO_BUCKET, member.name, f,
                length=member.size,
            )
    return len(members)
