"""AUT-139 follow behavior."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.models.user import User
from app.social import models as sm

STUB_USER = __import__("types").SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")


@pytest_asyncio.fixture(scope="module")
async def db_env():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(User(id="u2", display_name="Bob", email="bob@test.com", hashed_password="x"))
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
    yield app, maker


@pytest.mark.asyncio
async def test_follow_unfollow_and_list(env):
    app, _ = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/follow", json={"user_id": "u2"})
        assert r.status_code == 201, r.text
        r = await c.get("/social/follows")
        assert r.status_code == 200
        assert "u2" in r.json()["items"][0]["user_id"]
        r = await c.delete("/social/follow?user_id=u2")
        assert r.status_code == 204
        r = await c.get("/social/follows")
        assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_follow_requires_target(env):
    app, _ = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/follow", json={})
        assert r.status_code == 422
