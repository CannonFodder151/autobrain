"""Tests for AUT-501 My Builds: GET /social/my-posts and PATCH /social/posts/{id}.

Runs offline: own sqlite engine + dependency overrides; federation and MinIO
calls are stubbed.  Run: cd backend && python3 -m pytest tests/test_social_my_builds.py -q
"""

import os
import types

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.social import federation
from app.social import models as sm
from app.social.rate_limit import _window

ALICE = types.SimpleNamespace(id="alice", display_name="Alice", free_account=False, role="user")
BOB = types.SimpleNamespace(id="bob", display_name="Bob", free_account=False, role="user")


@pytest_asyncio.fixture(scope="module")
async def db_env():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(sm.SocialServerConfig(
            id=1, feature_enabled=True, federation_enabled=False,
            server_name="Server A",
        ))
        await s.commit()
    yield maker, engine
    await engine.dispose()


@pytest_asyncio.fixture
async def env(db_env, monkeypatch):
    maker, _ = db_env
    app = FastAPI()
    app.include_router(social_api.router)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[deps.require_premium] = lambda: ALICE
    app.dependency_overrides[deps.require_premium_write] = lambda: ALICE
    app.dependency_overrides[social_api.require_social_feature] = lambda: None
    _window._hits.clear()

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(federation, "push_outbox", _noop)
    monkeypatch.setattr(federation, "push_event", _noop)
    monkeypatch.setattr(federation, "pull_inbox", lambda cfg: [])
    monkeypatch.setattr(federation, "pull_events", lambda cfg, after: {"events": [], "next_cursor": 0})

    async with maker() as session:
        await session.execute(sm.SocialBuild.__table__.delete())
        await session.execute(sm.SocialComment.__table__.delete())
        await session.execute(sm.SocialLike.__table__.delete())
        await session.execute(sm.SocialPhoto.__table__.delete())
        await session.execute(sm.SocialShareScope.__table__.delete())
        await session.commit()

    yield app, maker


async def _seed(maker, *, owner_id=None, caption="original", origin="local",
               remote_build_id=None):
    async with maker() as s:
        build = sm.SocialBuild(
            author_user_id=owner_id,
            author_display_name="Alice",
            title="Camry build",
            caption=caption,
            origin=origin,
            remote_build_id=remote_build_id,
            snapshot_json='{"specs":{"make":"Toyota","model":"Camry"},"mods":[],"photo_keys":[]}',
        )
        s.add(build)
        await s.commit()
        return build.id


@pytest.mark.asyncio
async def test_my_posts_returns_only_callers_builds(env):
    app, maker = env
    mine = await _seed(maker, owner_id="alice", caption="mine")
    await _seed(maker, owner_id="bob", caption="bobs")
    await _seed(maker, origin="remote", remote_build_id="r1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/social/my-posts")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = {i["id"] for i in items}
    assert ids == {mine}
    assert items[0]["caption"] == "mine"


@pytest.mark.asyncio
async def test_my_posts_excludes_unpublished(env):
    app, maker = env
    async with maker() as s:
        build = sm.SocialBuild(
            author_user_id="alice", author_display_name="Alice",
            title="Hidden", caption="gone", origin="local", status="hidden",
            snapshot_json='{}',
        )
        s.add(build)
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/social/my-posts")
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_update_caption_owner_ok(env):
    app, maker = env
    post_id = await _seed(maker, owner_id="alice")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch(f"/social/posts/{post_id}", json={"caption": "updated caption"})
    assert r.status_code == 200
    assert r.json()["caption"] == "updated caption"


@pytest.mark.asyncio
async def test_update_caption_clears_to_null(env):
    app, maker = env
    post_id = await _seed(maker, owner_id="alice")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch(f"/social/posts/{post_id}", json={"caption": None})
    assert r.status_code == 200
    assert r.json()["caption"] is None


@pytest.mark.asyncio
async def test_update_caption_non_owner_404(env):
    app, maker = env
    post_id = await _seed(maker, owner_id="bob")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch(f"/social/posts/{post_id}", json={"caption": "hijack"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_missing_post_404(env):
    app, _ = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.patch("/social/posts/nope", json={"caption": "x"})
    assert r.status_code == 404
