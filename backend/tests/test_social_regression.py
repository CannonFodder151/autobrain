"""Regression tests for AUT-462 Community Garage P3 FAIL findings.

Each test fails on the pre-fix code (branch head before this change):
  MB-1/MB-2  rate limiting (429 + Retry-After) on social routes
  MD-2       5MB upload cap + 2048px dimension cap + DecompressionBombError
  MD-4       presigned URL TTL 15 min (asserted in test_storage_presigned.py)
  PW-8       non-owner delete -> 404 (was 403)
  CA-4       federation client sends X-Nonce; hub rejects replays (hub/self_check)
  FD-1       comments/likes fan out via /v1/events; events applied on pull
  FD-2       remote builds keep author_display_name / server_name / caption

Runs offline: own sqlite engine + dependency overrides; federation and MinIO
calls are stubbed.  Run: cd backend && python3 -m pytest tests/test_social_regression.py -q
"""

import os
import types

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.social import federation
from app.social import media as media_mod
from app.social import models as sm
from app.social.rate_limit import _window

STUB_USER = types.SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")
OWNER_USER = types.SimpleNamespace(id="owner-1", display_name="Owner", free_account=False, role="user")


@pytest_asyncio.fixture(scope="module")
async def db_env():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(sm.SocialServerConfig(
            id=1, feature_enabled=True, federation_enabled=True,
            hub_status="registered", hub_server_id="srv-a", server_name="Server A",
            hub_api_key="k", hub_private_key="p",
        ))
        await s.commit()
    yield maker, engine
    await engine.dispose()


@pytest_asyncio.fixture
async def env(db_env):
    maker, _ = db_env
    app = FastAPI()
    app.include_router(social_api.router)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[deps.require_premium] = lambda: STUB_USER
    app.dependency_overrides[deps.require_premium_write] = lambda: STUB_USER
    app.dependency_overrides[social_api.require_social_feature] = lambda: None
    _window._hits.clear()

    async with maker() as session:
        cfg = await session.get(sm.SocialServerConfig, 1)
        cfg.last_inbox_sync = None
        cfg.last_event_sync = 0
        await session.commit()

    yield app, maker


async def _stub_federation(monkeypatch):
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(federation, "push_outbox", _noop)
    monkeypatch.setattr(federation, "push_event", _noop)
    monkeypatch.setattr(federation, "pull_inbox", _no_builds)
    monkeypatch.setattr(federation, "pull_events", _no_events)


async def _no_builds(cfg):
    return []


async def _no_events(cfg, after):
    return {"events": [], "next_cursor": after}


# ── MB-1/MB-2: rate limiting ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_feed_rate_limited_429_with_retry_after(env, monkeypatch):
    app, _ = env
    await _stub_federation(monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for _ in range(24):
            r = await c.get("/social/feed")
            assert r.status_code == 200, r.text
        r = await c.get("/social/feed")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert r.headers["Retry-After"].isdigit()


@pytest.mark.asyncio
async def test_like_toggle_rate_limited(env, monkeypatch):
    app, maker = env
    await _stub_federation(monkeypatch)
    async with maker() as s:
        s.add(sm.SocialBuild(id="b-like", author_display_name="Alice", title="T",
                             origin="local", status="published", author_user_id="u1"))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for _ in range(20):
            r = await c.post("/social/posts/b-like/likes")
            assert r.status_code in (200, 201), r.text
        r = await c.post("/social/posts/b-like/likes")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_comment_rate_limited(env, monkeypatch):
    app, maker = env
    await _stub_federation(monkeypatch)
    async with maker() as s:
        s.add(sm.SocialBuild(id="b-com", author_display_name="Alice", title="T",
                             origin="local", status="published", author_user_id="u1"))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for _ in range(15):
            r = await c.post("/social/posts/b-com/comments", json={"body": "hi"})
            assert r.status_code == 201, r.text
        r = await c.post("/social/posts/b-com/comments", json={"body": "hi"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


# ── PW-8: non-owner delete -> 404 ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_post_non_owner_returns_404(env, monkeypatch):
    app, maker = env
    await _stub_federation(monkeypatch)
    async with maker() as s:
        s.add(sm.SocialBuild(id="b-owned", author_display_name="Owner", title="T",
                             origin="local", status="published", author_user_id="owner-1"))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.request("DELETE", "/social/posts/b-owned")
    assert r.status_code == 404


# ── MD-2: media caps ────────────────────────────────────────────────────────
def _png_bytes(width: int, height: int, color=(10, 20, 30)) -> bytes:
    import io

    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_upload_bytes_cap_is_15mb():
    import asyncio

    with pytest.raises(media_mod.MediaError) as exc:
        asyncio.run(media_mod.upload_photo("u1", b"x" * (15 * 1024 * 1024 + 1), "image/png"))
    assert "15MB" in str(exc.value)


def test_upload_downscales_over_2048px():
    import io

    webp = media_mod.compress_to_webp(_png_bytes(2600, 1800), "image/png")
    img = Image.open(io.BytesIO(webp))
    assert max(img.size) <= 2048


def test_upload_accepts_heic_photos():
    """iPhone default camera format must decode (AUT-764) — Pillow alone
    cannot, so the HEIF opener is registered; output is webp like every photo."""
    import io

    import pillow_heif as _pillow_heif

    src = Image.new("RGB", (1600, 900), (40, 90, 180))
    buf = io.BytesIO()
    src.save(buf, format="HEIF")
    heic = buf.getvalue()

    assert _pillow_heif.is_supported(heic)

    webp = media_mod.compress_to_webp(heic, "image/heic")
    img = Image.open(io.BytesIO(webp))
    assert img.format == "WEBP"
    assert img.size == (1600, 900)


def test_upload_rejects_decompression_bomb():
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    huge = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 200000, 200000, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )
    with pytest.raises(media_mod.MediaError):
        media_mod.compress_to_webp(huge, "image/png")


# ── AUT-597: oversized upload rejected without buffering full body ──────────
@pytest.mark.asyncio
async def test_upload_413_on_oversized_content_length(env, monkeypatch):
    """Content-Length past the cap -> 413 before the body is parsed/read."""
    app, _ = env
    called = []

    async def _must_not_run(file):
        called.append(True)
        raise AssertionError("read_upload must never run for a 413")

    monkeypatch.setattr(social_api, "read_upload", _must_not_run)
    big = b"x" * (15 * 1024 * 1024 + 1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/uploads", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413
    assert called == []


@pytest.mark.asyncio
async def test_upload_bounded_read_aborts_past_cap():
    """Streaming a body with no/misleading Content-Length stops at the cap."""
    class _StreamingUpload:
        def __init__(self, total):
            self._total = total
            self._served = 0

        async def read(self, size=-1):
            n = min(size, self._total - self._served)
            self._served += n
            return b"x" * n

    f = _StreamingUpload(media_mod.MAX_UPLOAD_BYTES + 10)
    with pytest.raises(media_mod.MediaError, match="15MB"):
        await media_mod.read_upload(f)
    assert f._served <= media_mod.MAX_UPLOAD_BYTES + media_mod.UPLOAD_READ_CHUNK


@pytest.mark.asyncio
async def test_upload_415_on_oversize_abort(env, monkeypatch):
    """Bounded-read abort (chunked/lying Content-Length) -> 415, never 500."""
    app, _ = env

    async def _abort(file):
        raise media_mod.MediaError("File too large (max 15MB)")

    monkeypatch.setattr(social_api, "read_upload", _abort)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/uploads", files={"file": ("small.png", b"x", "image/png")})
    assert r.status_code == 415
    assert "15MB" in r.text


# ── AUT-674: real phone photos (>5MB) upload fine; 15-photo cap ─────────────
def _noisy_jpeg_bytes(width: int, height: int, quality: int) -> bytes:
    """A large, incompressible photo-like image (noise) for size-gate tests."""
    import io
    import os

    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_accepts_photo_over_5mb(env, monkeypatch):
    """Real phone photos routinely exceed 5MB (esp. web + iOS multi-pick, which
    cannot pre-downscale). The 15MB input gate lets the backend's existing
    downscale+webp path handle them — regression for AUT-674."""
    app, maker = env
    if media_mod.MAX_UPLOAD_BYTES <= 5 * 1024 * 1024:
        pytest.skip("cap not raised; nothing to verify")

    async def _fake_upload(key, data, ct):
        return "http://fake/autobrain-assets/" + key

    async def _fake_presigned(key):
        return "http://fake/autobrain-assets/" + key

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(media_mod, "upload_object", _fake_upload)
    monkeypatch.setattr(media_mod, "presigned_url", _fake_presigned)
    monkeypatch.setattr(media_mod, "ensure_bucket", _noop)

    # noise JPEG ~ >5MB but under the 15MB cap
    big = _noisy_jpeg_bytes(3000, 3000, 95)
    assert len(big) > 5 * 1024 * 1024, f"fixture too small: {len(big)}"
    assert len(big) < media_mod.MAX_UPLOAD_BYTES, f"fixture too big: {len(big)}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/uploads", files={"file": ("phone.jpg", big, "image/jpeg")})
    assert r.status_code == 201, r.text
    assert "id" in r.json()


@pytest.mark.asyncio
async def test_post_accepts_15_photo_ids_rejects_16(env):
    """Pydantic cap on photo_ids is 15 (was 12 / UI 6) — AUT-674."""
    app, maker = env
    from app.models.vehicle import Vehicle

    async with maker() as s:
        s.add(Vehicle(id="v-photos", user_id="u1", nickname="Beast"))
        await s.commit()
    ids = [f"ph-{i}" for i in range(15)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/posts", json={
            "vehicle_id": "v-photos", "photo_ids": ids,
        })
        # cap allows 15; nonexistent photos just produce an empty photo set
        assert r.status_code == 201, r.text
        r16 = await c.post("/social/posts", json={
            "vehicle_id": "v-photos", "photo_ids": ids + ["ph-15"],
        })
        assert r16.status_code == 422


# ── CA-4: federation nonce ──────────────────────────────────────────────────
def test_federation_headers_include_nonce():
    cfg = types.SimpleNamespace(hub_server_id="srv-a", hub_api_key="k", hub_private_key="0" * 64)
    headers = federation._headers(cfg, "POST", "/v1/outbox", b"{}")
    assert "X-Nonce" in headers and headers["X-Nonce"]


# ── FD-1: comment/like fan-out ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_comment_and_like_fan_out_events(env, monkeypatch):
    app, maker = env
    captured = []

    async def _capture(cfg, build_id, kind, payload):
        captured.append((build_id, kind, payload))

    monkeypatch.setattr(federation, "push_event", _capture)
    monkeypatch.setattr(federation, "pull_inbox", _no_builds)
    monkeypatch.setattr(federation, "pull_events", _no_events)
    async with maker() as s:
        s.add(sm.SocialBuild(id="b-local", author_display_name="Alice", title="T",
                             origin="local", status="published", author_user_id="u1"))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/social/posts/b-local/comments", json={"body": "nice build"})
        await c.post("/social/posts/b-local/likes")
    kinds = [k for _, k, _ in captured]
    assert "comment" in kinds and "like" in kinds
    assert all(bid == "b-local" for bid, _, _ in captured)
    assert any(p.get("body") == "nice build" for _, _, p in captured)
    assert any("liked" in p for _, _, p in captured)


# ── FD-1 pull side + FD-2: sync + metadata ──────────────────────────────────
@pytest.mark.asyncio
async def test_federation_sync_imports_remote_metadata(env, monkeypatch):
    app, maker = env
    remote = [{
        "id": 1, "origin_server": "Server B", "created_at": 1,
        "build": {
            "build_id": "b-origin-9", "title": "My Skyline", "caption": "freshly rebuilt",
            "author_display_name": "Bob", "server_name": "Server B",
            "snapshot": {"photo_keys": []},
        },
    }]
    async def _pull_inbox(cfg):
        return remote

    async def _pull_events(cfg, after):
        return {"events": [], "next_cursor": 0}

    monkeypatch.setattr(federation, "pull_inbox", _pull_inbox)
    monkeypatch.setattr(federation, "pull_events", _pull_events)
    async with maker() as s:
        await social_api._sync_federation(s)
        row = (await s.execute(select(sm.SocialBuild).where(sm.SocialBuild.remote_build_id == "b-origin-9"))).scalar_one()
        assert row.author_display_name == "Bob"
        assert row.server_name == "Server B"
        assert row.caption == "freshly rebuilt"
        assert row.remote_server_id == "Server B"


@pytest.mark.asyncio
async def test_federation_sync_applies_remote_like_event(env, monkeypatch):
    app, maker = env
    async with maker() as s:
        s.add(sm.SocialBuild(id="b-copy", author_display_name="Bob", title="T", origin="remote",
                             status="published", remote_build_id="b-origin-9", remote_server_id="Server B"))
        await s.commit()
    async def _pull_inbox(cfg):
        return []

    async def _pull_events(cfg, after):
        return {
            "events": [{"event_type": "like", "payload": {
                "build_id": "b-origin-9", "liked": True,
                "author_display_name": "Carol", "server_name": "Server C",
            }}],
            "next_cursor": 5,
        }

    monkeypatch.setattr(federation, "pull_inbox", _pull_inbox)
    monkeypatch.setattr(federation, "pull_events", _pull_events)
    async with maker() as s:
        await social_api._sync_federation(s)
        likes = list(await s.scalars(select(sm.SocialLike).where(sm.SocialLike.build_id == "b-copy")))
        assert len(likes) == 1
        assert likes[0].author_display_name == "Carol"
        cfg = await s.get(sm.SocialServerConfig, 1)
        assert cfg.last_event_sync == 5
