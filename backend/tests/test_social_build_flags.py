"""Regression tests for build reporting/moderation (AUT-883).

Covers: flag a build post (dedupe per user), flag a build comment (dedupe,
404 for comment-on-other-build), build entries surfacing in the admin review
hub with target="build", and admin delete of a build comment/post purging
them from the queue.

Runs offline: own sqlite engine + dependency overrides (mirror of
tests/test_issues_blog.py). Run: cd backend && python3 -m pytest
tests/test_social_build_flags.py -q
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import types

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import admin as admin_api
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.social import models as sm
from app.social.rate_limit import _user_window, _window

STUB_USER = types.SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")
ADMIN_USER = types.SimpleNamespace(id="admin-1", display_name="Admin", free_account=False, role="admin", social_banned=False)


@pytest_asyncio.fixture(scope="module")
async def db_env():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(sm.SocialServerConfig(
            id=1, feature_enabled=True, federation_enabled=False, server_name="Server A",
        ))
        await s.commit()
    yield maker, engine
    await engine.dispose()


@pytest_asyncio.fixture
async def env(db_env, monkeypatch):
    maker, _ = db_env
    app = FastAPI()
    app.include_router(social_api.router)
    app.include_router(admin_api.admin_ops)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[deps.require_premium] = lambda: STUB_USER
    app.dependency_overrides[deps.require_premium_write] = lambda: STUB_USER
    app.dependency_overrides[deps.require_admin] = lambda: ADMIN_USER
    app.dependency_overrides[social_api.require_social_feature] = lambda: None

    _window._hits.clear()
    _user_window._hits.clear()

    async with maker() as s:
        await s.execute(delete(sm.SocialBuildFlag))
        await s.execute(delete(sm.SocialComment))
        await s.execute(delete(sm.SocialBuild))
        await s.commit()
    yield app, maker


async def _new_build(maker, **kwargs):
    async with maker() as s:
        build = sm.SocialBuild(
            author_user_id=kwargs.get("author_user_id", "u1"),
            author_display_name=kwargs.get("author_display_name", "Alice"),
            server_name="Server A",
            title=kwargs.get("title", "R34 build"),
            caption=kwargs.get("caption"),
            origin=kwargs.get("origin", "local"),
            status=kwargs.get("status", "published"),
        )
        s.add(build)
        await s.commit()
        return build.id


async def _new_comment(maker, build_id, body="Nice build", author_user_id="u1"):
    async with maker() as s:
        c = sm.SocialComment(
            build_id=build_id, author_user_id=author_user_id,
            author_display_name="Helper", server_name="Server A", body=body,
        )
        s.add(c)
        await s.commit()
        return c.id


@pytest.mark.asyncio
async def test_flag_build_dedupe_and_comment_flag(env):
    """AUT-883: a build and each of its comments are flaggable once per user."""
    app, maker = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        pid = await _new_build(maker)
        cid = await _new_comment(maker, pid)

        r = await c.post(f"/social/posts/{pid}/flag", json={"reason": "Spam"})
        assert r.status_code == 201, r.text
        # same user cannot double-flag the same build
        r = await c.post(f"/social/posts/{pid}/flag", json={"reason": "again"})
        assert r.status_code == 409

        r = await c.post(f"/social/posts/{pid}/comments/{cid}/flag", json={"reason": "Abusive"})
        assert r.status_code == 201, r.text
        # same user cannot re-flag the same comment
        r = await c.post(f"/social/posts/{pid}/comments/{cid}/flag", json={"reason": "again"})
        assert r.status_code == 409

        # comment on another build 404s (no probing)
        other = await _new_build(maker, title="Other build")
        r = await c.post(f"/social/posts/{other}/comments/{cid}/flag", json={"reason": "x"})
        assert r.status_code == 404

        # empty reason rejected
        r = await c.post(f"/social/posts/{pid}/flag", json={"reason": "   "})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_build_flags_in_admin_review_and_delete(env):
    """AUT-883: build + comment flags surface in the review hub with
    target="build"; admin deletes purge the queue."""
    app, maker = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        pid = await _new_build(maker, author_user_id="u2", author_display_name="Bob", title="Bad build")
        cid = await _new_comment(maker, pid, body="Bad comment", author_user_id="u2")

        assert (await c.post(f"/social/posts/{pid}/flag", json={"reason": "Misleading"})).status_code == 201
        assert (await c.post(f"/social/posts/{pid}/comments/{cid}/flag", json={"reason": "Abusive"})).status_code == 201

        r = await c.get("/admin/issues/review")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        build_items = [i for i in items if i["target"] == "build"]
        assert len(build_items) == 2
        assert {i["kind"] for i in build_items} == {"post", "comment"}
        assert all(i["post_id"] == pid for i in build_items)
        assert all(i["post_author_display_name"] == "Bob" for i in build_items)
        comment_item = next(i for i in build_items if i["kind"] == "comment")
        assert comment_item["comment_id"] == cid
        assert comment_item["comment_body"] == "Bad comment"

        # admin deletes the comment -> only the post flag remains
        assert (await c.delete(f"/admin/social/comments/{cid}")).status_code == 204
        items = (await c.get("/admin/issues/review")).json()["items"]
        build_items = [i for i in items if i["target"] == "build" and i["post_id"] == pid]
        assert [i["kind"] for i in build_items] == ["post"]

        # admin deletes the build -> gone from review entirely
        assert (await c.delete(f"/admin/social/posts/{pid}")).status_code == 204
        items = (await c.get("/admin/issues/review")).json()["items"]
        assert all(i["post_id"] != pid for i in items)


@pytest.mark.asyncio
async def test_admin_delete_build_purges_related_rows(env):
    """AUT-883: admin build delete cascades comments, likes and flags."""
    app, maker = env
    from app.social.models import SocialLike

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        pid = await _new_build(maker)
        cid = await _new_comment(maker, pid)
        async with maker() as s:
            s.add(SocialLike(build_id=pid, author_user_id="u2", author_display_name="Eve"))
            await s.commit()
        assert (await c.post(f"/social/posts/{pid}/flag", json={"reason": "Spam"})).status_code == 201
        assert (await c.post(f"/social/posts/{pid}/comments/{cid}/flag", json={"reason": "Spam"})).status_code == 201

        assert (await c.delete(f"/admin/social/posts/{pid}")).status_code == 204
        async with maker() as s:
            assert await s.get(sm.SocialBuild, pid) is None
            assert await s.get(sm.SocialComment, cid) is None
            assert (await s.scalar(
                select(SocialLike).where(SocialLike.build_id == pid)
            )) is None
            assert (await s.scalar(
                select(sm.SocialBuildFlag).where(sm.SocialBuildFlag.build_id == pid)
            )) is None
