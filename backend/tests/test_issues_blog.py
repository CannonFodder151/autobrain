"""Regression tests for the Community Garage Issues Blog (AUT-627, AUT-643).

Covers: plaintext sanitisation, deterministic auto-tags, blog list filters +
keyset cursor pagination, answer pinning (one answer per post), flag
dedupe/caps, hidden-post exclusion from browse + search, community (non
vehicle-scoped) search, and PW-8 404-for-non-owners on edit/delete/answer.

Runs offline: own sqlite engine + dependency overrides; the embedding router
is disabled (returns None) so search exercises the keyword-only path.
Run: cd backend && python3 -m pytest tests/test_issues_blog.py -q
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import types

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1 import issues as issues_api
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.social import models as sm
from app.social.rate_limit import _user_window, _window
from app.services.search import ENTITY_TYPES, semantic_search

STUB_USER = types.SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")
FREE_USER = types.SimpleNamespace(id="free-1", display_name="Freeloader", free_account=True, role="user")


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
async def env(db_env):
    maker, _ = db_env
    app = FastAPI()
    app.include_router(issues_api.router)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[deps.require_premium] = lambda: STUB_USER
    app.dependency_overrides[deps.require_premium_write] = lambda: STUB_USER
    app.dependency_overrides[social_api.require_social_feature] = lambda: None
    _window._hits.clear()
    _user_window._hits.clear()

    from sqlalchemy import delete

    async with maker() as s:
        await s.execute(delete(sm.SocialIssueFlag))
        await s.execute(delete(sm.SocialIssueComment))
        await s.execute(delete(sm.SocialIssuePost))
        await s.commit()
    yield app, maker


async def _new_issue(maker, **kwargs):
    async with maker() as s:
        post = sm.SocialIssuePost(
            author_user_id=kwargs.get("author_user_id", "u1"),
            author_display_name=kwargs.get("author_display_name", "Alice"),
            server_name=kwargs.get("server_name", "Server A"),
            title=kwargs.get("title", "Engine won't start"),
            body=kwargs.get("body", "Cold mornings, the starter turns but the engine never catches."),
            tags=kwargs.get("tags", ["engine", "starting"]),
            status=kwargs.get("status", "open"),
            status_hidden=kwargs.get("status_hidden", False),
            origin=kwargs.get("origin", "local"),
        )
        s.add(post)
        await s.commit()
        return post.id


async def _new_comment(maker, post_id, body="Try a new battery", author_user_id="u1"):
    async with maker() as s:
        c = sm.SocialIssueComment(
            post_id=post_id, author_user_id=author_user_id,
            author_display_name="Helper", server_name="Server A", body=body,
        )
        s.add(c)
        await s.commit()
        return c.id


@pytest.mark.asyncio
async def test_create_strips_control_chars_and_detects_tags(env):
    app, maker = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/issues", json={
            "title": "Brake squeal\x00on hard stops",
            "body": "Brakes squeal and make a loud noise\x07 when braking hard.",
        })
    assert r.status_code == 201, r.text
    data = r.json()
    # control chars replaced with spaces (NUL/bleep -> spaces)
    assert "\x00" not in data["title"] and data["title"] == "Brake squeal on hard stops"
    assert "\x07" not in data["body"]
    assert data["body"].startswith("Brakes squeal and make a loud noise")
    assert data["status"] == "open"
    assert "brakes" in data["tags"] and "noise" in data["tags"]
    assert data["is_mine"] is True


@pytest.mark.asyncio
async def test_create_requires_premium(env):
    app, _ = env
    # Free account: run the REAL entitlement chain end-to-end — override only
    # get_current_user so require_premium's free_account check fires (403).
    app.dependency_overrides.pop(deps.require_premium, None)
    app.dependency_overrides.pop(deps.require_premium_write, None)
    app.dependency_overrides[deps.get_current_user] = lambda: FREE_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/issues", json={"title": "Hi", "body": "Engine help"})
    assert r.status_code == 403
    assert "premium" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_reverse_chron_filters_and_cursor(env):
    app, maker = env
    a = await _new_issue(maker, title="Clutch is slipping", body="Clutch pedal feels soft", tags=["clutch"])
    b = await _new_issue(maker, title="Overheating", body="Temp gauge climbs on the highway", tags=["overheating"])
    await _new_issue(maker, title="Overheating again", body="Coolant leaking everywhere", tags=["cooling"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/social/issues")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [i["id"] for i in items] == [
            i["id"] for i in sorted(items, key=lambda i: i["created_at"], reverse=True)
        ]

        # tag filter
        r = (await c.get("/social/issues", params={"tag": "clutch"})).json()
        assert [i["id"] for i in r["items"]] == [a]
        # status filter
        r = (await c.get("/social/issues", params={"status": "open"})).json()
        assert len(r["items"]) == 3
        # q filter with LIKE escaping: "_" must be literal, not a wildcard
        r = (await c.get("/social/issues", params={"q": "overheatin_"})).json()
        assert r["items"] == []
        r = (await c.get("/social/issues", params={"q": "overheating"})).json()
        assert len(r["items"]) == 2
        # unknown tag rejected
        r = await c.get("/social/issues", params={"tag": "made-up"})
        assert r.status_code == 400

        # keyset cursor pagination across all three posts
        seen = []
        cursor = None
        while True:
            params = {"limit": 1}
            if cursor:
                params["cursor"] = cursor
            page_resp = await c.get("/social/issues", params=params)
            page = page_resp.json()
            if "items" not in page:
                raise AssertionError(f"page failed: {page_resp.status_code} {page} | cursor={cursor!r} | seen={seen!r}")
            seen += [i["id"] for i in page["items"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
    assert len(seen) == 3 and b in seen and a in seen


@pytest.mark.asyncio
async def test_comment_and_mark_answer(env):
    app, maker = env
    pid = await _new_issue(maker, author_user_id="owner-1", author_display_name="Owner")
    cid = await _new_comment(maker, pid, author_user_id="owner-2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # neither post author nor comment author -> 404 (PW-8, no probing)
        r = await c.post(f"/social/issues/{pid}/comments/{cid}/answer")
        assert r.status_code == 404

        # post author adds a comment and pins it -> resolved
        pid2 = await _new_issue(maker, author_user_id="u1")
        r = await c.post(f"/social/issues/{pid2}/comments", json={"body": "Swap the battery"})
        assert r.status_code == 201
        my_cid = r.json()["id"]

        r = await c.post(f"/social/issues/{pid2}/comments/{my_cid}/answer")
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"

        detail = (await c.get(f"/social/issues/{pid2}")).json()
        assert detail["status"] == "resolved"
        assert detail["resolved_comment_id"] == my_cid
        answers = [cm for cm in detail["comments"] if cm["is_answer"]]
        assert [cm["id"] for cm in answers] == [my_cid]


@pytest.mark.asyncio
async def test_comment_body_capped_and_plaintext(env):
    app, maker = env
    pid = await _new_issue(maker)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/social/issues/{pid}/comments", json={"body": "a" * 2001})
        assert r.status_code == 422
        r = await c.post(f"/social/issues/{pid}/comments", json={"body": "ok\x1f\nfine"})
        assert r.status_code == 201
        assert "\x1f" not in r.json()["body"]


@pytest.mark.asyncio
async def test_flag_dedupe_and_rate_limit(env):
    app, maker = env
    pids = [await _new_issue(maker) for _ in range(5)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # first flag ok
        assert (await c.post(f"/social/issues/{pids[0]}/flag", json={"reason": "Spam"})).status_code == 201
        # same user cannot double-flag the same post
        assert (await c.post(f"/social/issues/{pids[0]}/flag", json={"reason": "again"})).status_code == 409
        # 3 more flags (5 attempts total incl. the dedupe 409) then the cap trips
        for pid in pids[1:4]:
            assert (await c.post(f"/social/issues/{pid}/flag", json={"reason": "Spam"})).status_code == 201
        pid6 = await _new_issue(maker)
        r = await c.post(f"/social/issues/{pid6}/flag", json={"reason": "Spam"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_hidden_excluded_from_browse(env):
    app, maker = env
    await _new_issue(maker, title="Visible engine problem")
    hidden = await _new_issue(maker, title="Hidden engine problem", status_hidden=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        items = (await c.get("/social/issues")).json()["items"]
        assert all(i["id"] != hidden for i in items)
        assert (await c.get(f"/social/issues/{hidden}")).status_code == 404


@pytest.mark.asyncio
async def test_non_owner_edit_delete_404(env):
    app, maker = env
    pid = await _new_issue(maker, author_user_id="owner-1", author_display_name="Owner")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/social/issues/{pid}", json={"title": "Hijack"})
        assert r.status_code == 404
        r = await c.request("DELETE", f"/social/issues/{pid}")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_owner_patch_success_path(env):
    """Owner edits their own post -> 200 with the refreshed payload (regression
    for AUT-665: onupdate=func.now() expires updated_at after commit, and the
    async lazy load raised MissingGreenlet -> HTTP 500)."""
    app, maker = env
    pid = await _new_issue(maker, author_user_id="u1", title="Brake squeal", body="Only when cold")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/social/issues/{pid}", json={"title": "Brake squeal fixed?", "status": "answered"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == pid
        assert data["title"] == "Brake squeal fixed?"
        assert data["status"] == "answered"
        assert "updated_at" in data and data["updated_at"]
        # updated_at bumped after the edit
        detail = (await c.get(f"/social/issues/{pid}")).json()
        assert detail["updated_at"] >= data["updated_at"]

        # body-only patch still returns the full payload (updated_at not expired)
        r = await c.patch(f"/social/issues/{pid}", json={"body": "Warm weather fixed it"})
        assert r.status_code == 200, r.text
        assert r.json()["body"] == "Warm weather fixed it"
        assert r.json()["updated_at"]


@pytest.mark.asyncio
async def test_search_issue_is_community_not_vehicle_scoped(env):
    """Issues appear in search for any vehicle scope (including none) and
    hidden posts are excluded (keyword path, embeddings disabled)."""
    app, maker = env
    visible = await _new_issue(maker, title="Engine stalling at idle", body="Engine dies at lights")
    await _new_issue(maker, title="Engine stalling hidden", body="Engine dies too", status_hidden=True)

    async with maker() as s:
        results = await semantic_search(
            db=s, query="engine stalling", vehicle_ids=[], entity_types=["issue"], limit=10
        )
    ids = [r["id"] for r in results]
    assert visible in ids
    assert all(r["type"] == "issue" and r["vehicle_id"] is None for r in results)
    assert not any(r["title"].startswith("Engine stalling hidden") for r in results)

    assert "issue" in ENTITY_TYPES


@pytest.mark.asyncio
async def test_search_route_hides_issues_from_free_accounts(env):
    """Issues are premium-gated: global search must never surface them to a
    free account (server-side, mirrors the blog routes' entitlement)."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.v1 import search as search_api

    _, maker = env
    await _new_issue(maker, title="Engine stalling at idle", body="Engine dies at lights")

    s_app = FastAPI()
    s_app.include_router(search_api.router)

    async def _override_get_db():
        async with maker() as session:
            yield session

    s_app.dependency_overrides[get_db] = _override_get_db
    s_app.dependency_overrides[deps.get_current_user] = lambda: FREE_USER

    async with AsyncClient(transport=ASGITransport(app=s_app), base_url="http://test") as c:
        r = await c.get("/search", params={"q": "engine", "entity_types": "issue"})
        assert r.status_code == 200
        assert r.json() == []
        # global search for a free account excludes issue results entirely
        r = await c.get("/search", params={"q": "engine"})
        assert r.status_code == 200
        assert all(item["type"] != "issue" for item in r.json())
    # premium user sees the community issue in global search
    s_app.dependency_overrides[deps.get_current_user] = lambda: STUB_USER
    async with AsyncClient(transport=ASGITransport(app=s_app), base_url="http://test") as c:
        r = await c.get("/search", params={"q": "engine stalling"})
        assert r.status_code == 200
        assert any(item["type"] == "issue" for item in r.json())
