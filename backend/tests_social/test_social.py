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


def test_federation_signing_interop() -> None:
    """Client keypair/signature scheme must match the hub verifier (AUT-333)."""
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from app.social.federation import _canonical, _sign, generate_keypair

    priv, pub = generate_keypair()
    assert len(pub) == 64  # hex-encoded ed25519 public key
    ts = "1234567890"
    nonce = "abcd"
    body = b'{"build_id":"b1","title":"hi"}'
    canonical = _canonical("POST", "/v1/outbox", ts, nonce, body)
    sig = _sign(priv, canonical)

    # Mirror of autobrain-federation-hub app/security.py::verify_signature
    pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub))
    pk.verify(base64.b64decode(sig), canonical)

    tampered = _canonical("POST", "/v1/outbox", ts, nonce, b'{"build_id":"b1","title":"EVIL"}')
    with pytest.raises(InvalidSignature):
        pk.verify(base64.b64decode(_sign(priv, tampered)), canonical)


def test_federation_register_sends_hosted_registration_key(monkeypatch) -> None:
    """AUT-525: register() must forward the hosted registration key to the hub.

    Self-hosted servers send an empty string (hub rejects `hosted=true` without
    a valid key); hosted stacks inject the Paperclip secret at deploy time.
    """
    import asyncio
    import json

    import httpx

    from app.core.config import settings
    from app.social import federation
    from app.social.models import SocialServerConfig

    captured: dict = {}

    async def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"server_id": "abcd", "api_key": "k"})

    monkeypatch.setattr(settings, "SOCIAL_FEDERATION_HOSTED", True)
    monkeypatch.setattr(settings, "SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY", "hub-secret")
    monkeypatch.setattr(
        federation, "_hub_url", lambda cfg: "https://hub.example.invalid"
    )
    _orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig_client(transport=httpx.MockTransport(_handler)))

    async def _run():
        await federation.register(
            SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True),
            "my-server", "me@example.com", "a" * 64,
        )

    asyncio.run(_run())
    assert captured["url"].endswith("/v1/register")
    payload = json.loads(captured["body"])
    assert payload["hosted"] is True
    assert payload["registration_key"] == "hub-secret"

    # self-hosted: key defaults to empty, never a hardcoded secret
    monkeypatch.setattr(settings, "SOCIAL_FEDERATION_HOSTED", False)
    monkeypatch.setattr(settings, "SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY", "")
    captured.clear()
    asyncio.run(_run())
    payload = json.loads(captured["body"])
    assert payload["hosted"] is False
    assert payload["registration_key"] == ""


@pytest.mark.asyncio
async def test_register_pending_reflected(monkeypatch) -> None:
    """AUT-731: the hub's approval workflow (AUT-525) returns `status: pending`
    for new registrations. The client must reflect that instead of claiming
    `registered`, so federation isn't silently dead until the operator approves."""
    import httpx

    from app.social import federation

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "server_id": "deadbeef", "api_key": "k",
            "status": "pending", "license_status": "pending_checkout",
        })

    _orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig_client(transport=httpx.MockTransport(_handler)))
    monkeypatch.setattr(federation, "_hub_url", lambda cfg: "https://hub.example.invalid")

    from app.social.models import SocialServerConfig

    async with _SessionLocal() as db:
        admin = await _new_user(db, "reg-pending@example.com", "RegAdmin", role="admin")
        admin_token = create_access_token(admin.id)
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 server_name="Reg", server_email="reg@example.com",
                                 hub_status="unregistered")
        await db.merge(cfg)
        await db.commit()
    async with await _client(admin_token) as c:
        got = await c.get("/api/v1/admin/social")
        assert got.json()["hub_status"] == "unregistered"
        reg = await c.post("/api/v1/admin/social/register")
        assert reg.status_code == 200, reg.text
        assert reg.json()["hub_status"] == "pending"
        assert reg.json()["hub_server_id"] == "deadbeef"
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        assert cfg.hub_status == "pending"


@pytest.mark.asyncio
async def test_pending_registration_self_heals_on_approval(monkeypatch) -> None:
    """AUT-731: a `pending` registration flips to `registered` (and starts
    federating) once the hub operator approves it — checked against the hub's
    public status endpoint on feed load, no manual re-register needed."""
    async def _no_inbox(_cfg):
        return []

    async def _no_events(_cfg, after):
        return {"events": [], "next_cursor": 0}

    async def _status_pending(_cfg):
        return {"server_id": "deadbeef", "status": "pending", "license_status": "pending_checkout"}

    monkeypatch.setattr("app.social.federation.pull_inbox", _no_inbox)
    monkeypatch.setattr("app.social.federation.pull_events", _no_events)
    monkeypatch.setattr("app.social.federation.get_server_status", _status_pending)
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 hub_status="pending", hub_server_id="deadbeef",
                                 last_inbox_sync=None, last_event_sync=None)
        await db.merge(cfg)
        await db.commit()
        user = await _new_user(db, "pending@example.com", "Pending")
        token = create_access_token(user.id)
    async with await _client(token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        assert cfg.hub_status == "pending"  # still pending → not federating

    # hub operator approves → next feed flips it to registered and syncs
    async def _status_approved(_cfg):
        return {"server_id": "deadbeef", "status": "approved", "license_status": "active"}

    monkeypatch.setattr("app.social.federation.get_server_status", _status_approved)
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        cfg.last_inbox_sync = None  # force a fresh sync
        await db.commit()
    async with await _client(token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        assert cfg.hub_status == "registered"
        assert cfg.last_inbox_sync is not None


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
async def test_free_account_cannot_write() -> None:
    """Rev 4: every social write route is premium-gated (no paywall bypass)."""
    await _enable_feature(True)
    async with _SessionLocal() as db:
        free = await _new_user(db, "free2@example.com", "Free2", free=True)
        owner = await _new_user(db, "owner2@example.com", "Owner2")
        vehicle = await _new_vehicle(db, owner.id)
        token = create_access_token(free.id)
        vehicle_id = vehicle.id
    async with await _client(token) as c:
        for method, path, json_body in [
            ("POST", "/api/v1/social/posts", {"vehicle_id": vehicle_id}),
            ("POST", "/api/v1/social/posts/p1/comments", {"body": "hi"}),
            ("POST", "/api/v1/social/posts/p1/likes", None),
            ("POST", "/api/v1/social/posts/p1/share-link", None),
            ("DELETE", "/api/v1/social/posts/p1", None),
        ]:
            resp = await c.request(method, path, json=json_body)
            assert resp.status_code == 403, (method, path, resp.text)
            assert "premium" in resp.json()["detail"].lower()
    # upload is also premium-gated
    async with await _client(token) as c:
        resp = await c.post("/api/v1/social/uploads",
                            files={"file": ("a.png", b"xx", "image/png")})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_demo_read_only() -> None:
    await _enable_feature(True)
    async with _SessionLocal() as db:
        demo = await _new_user(db, "demo@example.com", "Demo", role="demo")
        owner = await _new_user(db, "owner3@example.com", "Owner3")
        vehicle = await _new_vehicle(db, owner.id)
        demo_token = create_access_token(demo.id)
        vehicle_id = vehicle.id
    async with await _client(demo_token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200  # demo can read
        created = await c.post("/api/v1/social/posts", json={"vehicle_id": vehicle_id})
        assert created.status_code == 403  # demo cannot write
        assert "read-only" in created.json()["detail"].lower()


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


# --- edit build (AUT-675) ----------------------------------------------------


@pytest.mark.asyncio
async def test_edit_build_title_photos_scope(monkeypatch) -> None:
    """AUT-675: edit renames a build, reorders/adds/removes photos and changes
    the share scope — all after the initial share."""
    async def _fake_upload(user_id, data, content_type=None):
        return (f"social/{user_id}/x.webp", "http://assets/x.webp", 640, 480)

    monkeypatch.setattr("app.api.v1.social.upload_photo", _fake_upload)
    await _enable_feature(True)
    async with _SessionLocal() as db:
        owner = await _new_user(db, "editor@example.com", "Editor")
        vehicle = await _new_vehicle(db, owner.id)
        other = await _new_user(db, "peek@example.com", "Peek")
        token = create_access_token(owner.id)
        other_token = create_access_token(other.id)
        vehicle_id = vehicle.id
    async with await _client(token) as c:
        p1 = (await c.post("/api/v1/social/uploads",
                           files={"file": ("a.webp", b"aaaa", "image/webp")})).json()
        p2 = (await c.post("/api/v1/social/uploads",
                           files={"file": ("b.webp", b"bbbb", "image/webp")})).json()
        p3 = (await c.post("/api/v1/social/uploads",
                           files={"file": ("c.webp", b"cccc", "image/webp")})).json()
        created = await c.post("/api/v1/social/posts", json={
            "vehicle_id": vehicle_id,
            "title": "Project Sky",
            "caption": "In progress",
            "photo_ids": [p1["id"], p2["id"], p3["id"]],
        })
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["title"] == "Project Sky"
        assert body["photo_ids"] == [p1["id"], p2["id"], p3["id"]]
        assert "odometer_km" not in body["snapshot"]["specs"]
        post_id = body["id"]

        # rename + drop p3 + reorder (p2 first) + widen scope
        updated = await c.patch(f"/api/v1/social/posts/{post_id}", json={
            "title": "Project Sky II",
            "caption": "Paint done",
            "photo_ids": [p2["id"], p1["id"]],
            "share_scope": {"allow_odometer": True, "allow_notes": True},
        })
        assert updated.status_code == 200, updated.text
        ub = updated.json()
        assert ub["title"] == "Project Sky II"
        assert ub["caption"] == "Paint done"
        assert ub["photo_ids"] == [p2["id"], p1["id"]]
        assert ub["snapshot"]["specs"]["odometer_km"] == 142000
        assert ub["snapshot"]["notes"]

        # feed reflects the new name + order
        feed = (await c.get("/api/v1/social/feed")).json()["items"]
        mine = next(i for i in feed if i["id"] == post_id)
        assert mine["title"] == "Project Sky II"
        assert mine["photo_ids"] == [p2["id"], p1["id"]]

        # dropped photo is free again (can be re-attached)
        detail = (await c.get(f"/api/v1/social/posts/{post_id}")).json()
        assert p3["id"] not in detail["photo_ids"]

        # F3: caption None = unchanged; explicit "" clears
        keep = await c.patch(f"/api/v1/social/posts/{post_id}", json={"caption": None})
        assert keep.json()["caption"] == "Paint done"
        cleared = await c.patch(f"/api/v1/social/posts/{post_id}", json={"caption": ""})
        assert cleared.json()["caption"] is None

        # hide photos, then verify non-owner sees no photo_ids (F1)
        hidden = await c.patch(f"/api/v1/social/posts/{post_id}",
                               json={"share_scope": {"allow_photos": False}})
        assert hidden.json()["photo_ids"] == [p2["id"], p1["id"]]

        # non-owners cannot edit (404, same as delete — PW-8)
        async with await _client(other_token) as oc:
            denied = await oc.patch(f"/api/v1/social/posts/{post_id}",
                                    json={"title": "Hacked"})
            assert denied.status_code == 404
            # F1: non-owner never sees photo ids, even for published builds
            detail = (await oc.get(f"/api/v1/social/posts/{post_id}")).json()
            assert detail["photo_ids"] == []

        # QA#2: a photo attached to this build cannot be hijacked into another
        second = await c.post("/api/v1/social/posts", json={"vehicle_id": vehicle_id})
        second_id = second.json()["id"]
        hijack = await c.patch(f"/api/v1/social/posts/{second_id}",
                               json={"photo_ids": [p1["id"]]})
        assert hijack.status_code == 400, hijack.text

        gone2 = await c.delete(f"/api/v1/social/posts/{second_id}")
        assert gone2.status_code == 204
        gone = await c.delete(f"/api/v1/social/posts/{post_id}")
        assert gone.status_code == 204


@pytest.mark.asyncio
async def test_edit_build_rejects_unknown_photos(monkeypatch) -> None:
    async def _fake_upload(user_id, data, content_type=None):
        return (f"social/{user_id}/x.webp", "http://assets/x.webp", 640, 480)

    monkeypatch.setattr("app.api.v1.social.upload_photo", _fake_upload)
    await _enable_feature(True)
    async with _SessionLocal() as db:
        owner = await _new_user(db, "editor2@example.com", "Editor2")
        vehicle = await _new_vehicle(db, owner.id)
        token = create_access_token(owner.id)
        vehicle_id = vehicle.id
    async with await _client(token) as c:
        created = await c.post("/api/v1/social/posts", json={"vehicle_id": vehicle_id})
        post_id = created.json()["id"]
        bad = await c.patch(f"/api/v1/social/posts/{post_id}",
                            json={"photo_ids": ["no-such-photo"]})
        assert bad.status_code == 400
        await c.delete(f"/api/v1/social/posts/{post_id}")


# --- federation on/off -------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_search_filters_posts() -> None:
    """?q= matches title, caption, author and server name (AUT-530)."""
    await _enable_feature(True)
    async with _SessionLocal() as db:
        owner = await _new_user(db, "search@example.com", "Kai")
        vehicle = await _new_vehicle(db, owner.id)
        token = create_access_token(owner.id)
        vehicle_id = vehicle.id
    async with await _client(token) as c:
        await c.post("/api/v1/social/posts", json={
            "vehicle_id": vehicle_id, "caption": "Twin turbo done",
        })
        await c.post("/api/v1/social/posts", json={
            "vehicle_id": vehicle_id, "caption": "Widebody kit",
        })

        all_items = (await c.get("/api/v1/social/feed")).json()["items"]
        assert len(all_items) == 2

        by_caption = (await c.get("/api/v1/social/feed?q=turbo")).json()["items"]
        assert len(by_caption) == 1
        assert "turbo" in by_caption[0]["caption"]

        by_author = (await c.get("/api/v1/social/feed?q=Kai")).json()["items"]
        assert len(by_author) == 2

        none = (await c.get("/api/v1/social/feed?q=no-such-thing")).json()["items"]
        assert none == []


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

    async def _no_events(_cfg, after):
        return {"events": [], "next_cursor": 0}

    monkeypatch.setattr("app.social.federation.pull_inbox", _fake_pull)
    monkeypatch.setattr("app.social.federation.pull_events", _no_events)
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 hub_status="registered", hub_server_id="me",
                                 hub_api_key="k", hub_private_key="ab" * 32,
                                 last_inbox_sync=None, last_event_sync=None)
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


@pytest.mark.asyncio
async def test_feed_survives_empty_hub_event_cursor(monkeypatch) -> None:
    """AUT-694: the hub returns `next_cursor: 0` with no pending events, and the
    first sync crashed on `int(0 or None)` -> 500 on the whole feed."""
    async def _no_inbox(_cfg):
        return []

    async def _empty_events(_cfg, after):
        return {"events": [], "next_cursor": 0}

    monkeypatch.setattr("app.social.federation.pull_inbox", _no_inbox)
    monkeypatch.setattr("app.social.federation.pull_events", _empty_events)
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 hub_status="registered", hub_server_id="me",
                                 last_inbox_sync=None, last_event_sync=None)
        await db.merge(cfg)
        await db.commit()
        user = await _new_user(db, "cursor@example.com", "Cursor")
        token = create_access_token(user.id)
    async with await _client(token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200, feed.text
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        assert cfg.last_event_sync == 0


@pytest.mark.asyncio
async def test_feed_survives_malformed_hub_payloads(monkeypatch) -> None:
    """AUT-694: federated payloads with unexpected shapes must never 500 the
    feed (errors are logged, feed keeps serving local builds)."""
    async def _bad_inbox(_cfg):
        return [
            {"id": 1, "build": "not-a-dict", "created_at": "x"},
            {"id": 2, "origin_server": "o", "build": {
                "build_id": "hub-bad", "title": "S",
                "snapshot": "just a string"}},
        ]

    async def _bad_events(_cfg, after):
        return {"events": [
            {"id": 1, "event_type": "comment", "payload": "not-a-dict"},
        ], "next_cursor": 1}

    monkeypatch.setattr("app.social.federation.pull_inbox", _bad_inbox)
    monkeypatch.setattr("app.social.federation.pull_events", _bad_events)
    async with _SessionLocal() as db:
        cfg = SocialServerConfig(id=1, feature_enabled=True, federation_enabled=True,
                                 hub_status="registered", hub_server_id="me",
                                 last_inbox_sync=None, last_event_sync=None)
        await db.merge(cfg)
        await db.commit()
        user = await _new_user(db, "badhub@example.com", "BadHub")
        token = create_access_token(user.id)
    async with await _client(token) as c:
        feed = await c.get("/api/v1/social/feed")
        assert feed.status_code == 200, feed.text
    async with _SessionLocal() as db:
        cfg = await db.get(SocialServerConfig, 1)
        assert cfg.last_event_sync == 1


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
