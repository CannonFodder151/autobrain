"""Tests for AUT-896: POST /social/posts/{id}/report.

Covers: local flag persistence, federation push (local id vs remote_build_id),
dedupe on repeat report, 404 for unknown posts. Runs offline with the same
stubbing pattern as test_social_my_builds.py.
"""

import os
import types

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
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


@pytest_asyncio.fixture(scope="module")
async def db_env():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(sm.SocialServerConfig(
            id=1, feature_enabled=True, federation_enabled=True,
            server_name="Server A", hub_status="registered",
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

    pushed = []

    async def _record_push(cfg, build_id, *a, **k):
        pushed.append(build_id)

    monkeypatch.setattr(federation, "push_event", _record_push)
    monkeypatch.setattr(federation, "push_report", _record_push)

    async with maker() as session:
        await session.execute(sm.SocialBuild.__table__.delete())
        await session.execute(sm.SocialBuildFlag.__table__.delete())
        await session.commit()

    yield app, maker, pushed


async def _seed(maker, *, origin="local", remote_build_id=None):
    async with maker() as s:
        build = sm.SocialBuild(
            author_user_id="bob", author_display_name="Bob",
            title="Camry build", caption="needs work",
            origin=origin, remote_build_id=remote_build_id,
            snapshot_json='{}',
        )
        s.add(build)
        await s.commit()
        return build.id


@pytest.mark.asyncio
async def test_report_local_post_persists_and_pushes_local_id(env):
    app, maker, pushed = env
    post_id = await _seed(maker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/social/posts/{post_id}/report", json={"reason": "spam"})
    assert r.status_code == 201
    assert r.json() == {"reported": True}
    assert pushed == [post_id]
    async with maker() as s:
        flags = (await s.execute(select(sm.SocialBuildFlag))).scalars().all()
        assert len(flags) == 1
        assert flags[0].reason == "spam"


@pytest.mark.asyncio
async def test_report_remote_post_pushes_origin_build_id(env):
    app, maker, pushed = env
    post_id = await _seed(maker, origin="remote", remote_build_id="orig-1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/social/posts/{post_id}/report", json={"reason": "misleading"})
    assert r.status_code == 201
    assert pushed == ["orig-1"]


@pytest.mark.asyncio
async def test_report_repeat_updates_reason_not_duplicate(env):
    app, maker, pushed = env
    post_id = await _seed(maker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        first = await c.post(f"/social/posts/{post_id}/report", json={"reason": "spam"})
        second = await c.post(f"/social/posts/{post_id}/report", json={"reason": "abuse"})
    assert first.status_code == 201 and second.status_code == 201
    async with maker() as s:
        flags = (await s.execute(select(sm.SocialBuildFlag))).scalars().all()
        assert len(flags) == 1
        assert flags[0].reason == "abuse"


@pytest.mark.asyncio
async def test_report_missing_post_404(env):
    app, _, pushed = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/social/posts/nope/report", json={"reason": "spam"})
    assert r.status_code == 404
    assert pushed == []


@pytest.mark.asyncio
async def test_report_requires_reason(env):
    app, maker, _ = env
    post_id = await _seed(maker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/social/posts/{post_id}/report", json={"reason": ""})
    assert r.status_code == 422
