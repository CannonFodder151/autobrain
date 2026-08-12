"""Community Garage social routes + media/snapshot tests (AUT-332).

Self-contained: builds its own sqlite engine and overrides the app's get_db
dependency, so this module runs standalone (no Postgres/MinIO needed) and never
touches the compose test database.
"""

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.mkdtemp() + "/social-test.sqlite"
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["POSTGRES_USER"] = "u"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["MINIO_ACCESS_KEY"] = "k"
os.environ["MINIO_SECRET_KEY"] = "s"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.mod import Modification
from app.models.user import User
from app.models.vehicle import Vehicle
from app.social.media import compress_to_webp
from app.social.models import SocialBuild, SocialServerConfig
from app.social.snapshot import build_snapshot, dumps, loads

_engine = create_async_engine(os.environ["DATABASE_URL"])
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


@pytest.fixture(scope="module", autouse=True)
def _db_setup():
    import asyncio

    async def _setup() -> None:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _override_get_db():
        async with _SessionLocal() as session:
            yield session

    asyncio.run(_setup())
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    asyncio.run(_engine.dispose())


async def _new_user(db, email: str, display_name: str, free: bool = False, role: str = "user") -> User:
    user = User(
        email=email,
        display_name=display_name,
        hashed_password=hash_password("hunter22"),
        role=role,
        free_account=free,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _new_vehicle(db, user_id: str, nickname: str = "R34 Skyline") -> Vehicle:
    vehicle = Vehicle(user_id=user_id, nickname=nickname, make="Nissan", model="Skyline GT-R",
                      year=2000, engine="RB26DETT", odometer_km=142000, condition="excellent")
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    db.add(Modification(vehicle_id=vehicle.id, name="Garrett turbo", category="performance", brand="Garrett"))
    await db.commit()
    return vehicle


async def _client(token: str | None = None) -> AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


async def _enable_feature(enabled: bool = True) -> None:
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=enabled, federation_enabled=False)
        await db.merge(cfg)
        await db.commit()


# --- pure functions ---------------------------------------------------------


def test_compress_to_webp() -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (200, 30, 30)).save(buf, format="PNG")
    webp = compress_to_webp(buf.getvalue(), "image/png")
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP"
    img = Image.open(io.BytesIO(webp))
    assert (img.width, img.height) == (32, 24)


@pytest.mark.asyncio
async def test_snapshot_deterministic() -> None:
    async with _SessionLocal() as db:
        user = await _new_user(db, "snap@example.com", "Snap")
        vehicle = await _new_vehicle(db, user.id)
        snap = await build_snapshot(db, vehicle, None, [])
        assert snap["title"] == "Nissan Skyline GT-R"
        assert snap["specs"]["make"] == "Nissan"
        assert "odometer_km" not in snap["specs"]  # default scope hides odometer
        assert snap["mods"][0]["name"] == "Garrett turbo"
        assert snap["mods"][0]["brand"] == "Garrett"
        assert snap["photo_keys"] == []
        assert loads(dumps(snap)) == snap


# --- feature gate + entitlement (rev 4) -------------------------------------


@pytest.mark.asyncio
async def test_feature_disabled_shows_admin_message() -> None:
    await _enable_feature(False)
    try:
        async with _SessionLocal() as db:
            user = await _new_user(db, "gated@example.com", "Gated")
        token = create_access_token(user.id)
        async with await _client(token) as c:
            resp = await c.get("/api/v1/social/feed")
        assert resp.status_code == 403
        assert "Disabled by your admin" in resp.json()["detail"]
    finally:
        await _enable_feature(True)


@pytest.mark.asyncio
async def test_free_account_locked_out() -> None:
    await _enable_feature(True)
    async with _SessionLocal() as db:
        free = await _new_user(db, "free@example.com", "Free", free=True)
        token = create_access_token(free.id)
    async with await _client(token) as c:
        resp = await c.get("/api/v1/social/feed")
    assert resp.status_code == 403
    assert "premium" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthenticated_rejected() -> None:
    async with await _client() as c:
        resp = await c.get("/api/v1/social/feed")
    assert resp.status_code == 401


# --- happy path: create → feed → comment → like → share link -----------------


@pytest.mark.asyncio
async def test_social_happy_path() -> None:
    await _enable_feature(True)
    async with _SessionLocal() as db:
        owner = await _new_user(db, "owner@example.com", "Owner")
        vehicle = await _new_vehicle(db, owner.id)
        viewer = await _new_user(db, "viewer@example.com", "Viewer")
        owner_token = create_access_token(owner.id)
        viewer_token = create_access_token(viewer.id)
        vehicle_id = vehicle.id

    async with await _client(owner_token) as c:
        created = await c.post("/api/v1/social/posts", json={
            "vehicle_id": vehicle_id,
            "caption": "Twin turbo done",
            "share_scope": {"allow_odometer": False},
        })
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["title"] == "Nissan Skyline GT-R"
        assert body["snapshot"]["specs"]["make"] == "Nissan"
        assert "odometer_km" not in body["snapshot"]["specs"]
        assert body["snapshot"]["mods"][0]["name"] == "Garrett turbo"
        post_id = body["id"]

        detail = await c.get(f"/api/v1/social/posts/{post_id}")
        assert detail.status_code == 200
        assert detail.json()["caption"] == "Twin turbo done"

        comment = await c.post(f"/api/v1/social/posts/{post_id}/comments",
                               json={"body": "Clean build"})
        assert comment.status_code == 201, comment.text

        liked = await c.post(f"/api/v1/social/posts/{post_id}/likes")
        assert liked.status_code == 200
        assert liked.json()["liked"] is True
        assert liked.json()["like_count"] == 1

        link = await c.post(f"/api/v1/social/posts/{post_id}/share-link")
        assert link.status_code == 200
        token = link.json()["token"]

        await _enable_feature(True)
        resolved = await c.get(f"/api/v1/social/share/{token}")
        assert resolved.status_code == 200
        assert resolved.json()["id"] == post_id

        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200
        items = feed.json()["items"]
        assert any(i["id"] == post_id for i in items)
        assert items[0]["like_count"] == 1

        # viewer can comment + like someone else's build
        async with await _client(viewer_token) as vc:
            v_like = await vc.post(f"/api/v1/social/posts/{post_id}/likes")
            assert v_like.status_code == 200
            assert v_like.json()["like_count"] == 2
            comments = await vc.get(f"/api/v1/social/posts/{post_id}/comments")
            assert comments.status_code == 200
            assert len(comments.json()["items"]) == 1

        # unshare (takedown)
        gone = await c.delete(f"/api/v1/social/posts/{post_id}")
        assert gone.status_code == 204
        gone2 = await c.get(f"/api/v1/social/posts/{post_id}")
        assert gone2.status_code == 404


# --- federation on/off -------------------------------------------------------


@pytest.mark.asyncio
async def test_federation_off_feed_local_only() -> None:
    """With federation off and no hub configured, the feed still works."""
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=False,
                                 hub_status="unregistered")
        await db.merge(cfg)
        await db.commit()
        user = await _new_user(db, "local@example.com", "Local")
        vehicle = await _new_vehicle(db, user.id)
        vehicle_id = vehicle.id
        token = create_access_token(user.id)
    async with await _client(token) as c:
        created = await c.post("/api/v1/social/posts", json={"vehicle_id": vehicle_id})
        assert created.status_code == 201
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200
        assert all(i["origin"] == "local" for i in feed.json()["items"])


@pytest.mark.asyncio
async def test_inbox_pulls_remote_builds(monkeypatch) -> None:
    async def _fake_pull(_cfg):
        return [{
            "remote_build_id": "hub-1",
            "server_id": "server-b",
            "author_display_name": "Bob",
            "server_name": "Bob's Garage",
            "title": "Clubman build",
            "caption": "From another server",
            "snapshot": {"title": "Clubman build", "mods": [{"name": "Exhaust"}]},
        }]

    monkeypatch.setattr("app.social.federation.pull_inbox", _fake_pull)
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 hub_status="registered", hub_server_id="me")
        await db.merge(cfg)
        await db.commit()
        user = await _new_user(db, "hub@example.com", "Hub")
        token = create_access_token(user.id)
    async with await _client(token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200
        remote = [i for i in feed.json()["items"] if i["origin"] == "remote"]
        assert len(remote) == 1
        assert remote[0]["title"] == "Clubman build"
        assert remote[0]["author_display_name"] == "Bob"
        assert remote[0]["snapshot"]["mods"][0]["name"] == "Exhaust"
    async with _SessionLocal() as db:
        rows = list(await db.scalars(select(SocialBuild).where(SocialBuild.origin == "remote")))
        assert len(rows) == 1


# --- admin toggles ------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_toggles() -> None:
    async with _SessionLocal() as db:
        admin = await _new_user(db, "admin@example.com", "Admin", role="admin")
        admin_token = create_access_token(admin.id)
    async with await _client(admin_token) as c:
        got = await c.get("/api/v1/admin/social")
        assert got.status_code == 200
        assert got.json()["feature_enabled"] is True

        patched = await c.patch("/api/v1/admin/social",
                                json={"feature_enabled": False, "federation_enabled": True,
                                      "server_name": "AutoBrain HQ", "server_email": "ops@example.com"})
        assert patched.status_code == 200, patched.text
        got = await c.get("/api/v1/admin/social")
        assert got.json()["feature_enabled"] is False
        assert got.json()["federation_enabled"] is True

        # feature off → feed 403 for everyone, even premium
        async with _SessionLocal() as db:
            user = await _new_user(db, "user2@example.com", "User2")
            user_token = create_access_token(user.id)
        async with await _client(user_token) as c2:
            resp = await c2.get("/api/v1/social/feed")
            assert resp.status_code == 403

        # register with no hub configured → 502, hub_status=error
        reg = await c.post("/api/v1/admin/social/register")
        assert reg.status_code == 502
        got = await c.get("/api/v1/admin/social")
        assert got.json()["hub_status"] == "error"

        unreg = await c.post("/api/v1/admin/social/unregister")
        assert unreg.status_code == 200
        assert unreg.json()["hub_status"] == "unregistered"

        await c.patch("/api/v1/admin/social", json={"feature_enabled": True, "federation_enabled": False})


# --- upload -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_and_create_with_photo(monkeypatch) -> None:
    async def _fake_upload(user_id, data, content_type=None):
        return ("social/x/abc.webp", "http://assets/x.webp", 640, 480)

    monkeypatch.setattr("app.api.v1.social.upload_photo", _fake_upload)
    async with _SessionLocal() as db:
        user = await _new_user(db, "pic@example.com", "Pic")
        token = create_access_token(user.id)
    async with await _client(token) as c:
        resp = await c.post("/api/v1/social/uploads", files={"file": ("car.png", b"\x89PNG\r\n\x1a\nfakepng", "image/png")})
        assert resp.status_code == 201, resp.text
        photo_id = resp.json()["id"]
        assert photo_id
