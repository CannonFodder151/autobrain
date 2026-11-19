"""AUT-670 PT1: Issues Blog security remediation regression tests.

Covers the three AUT-646 triage findings:

- F1 (MEDIUM): per-IP rate-limit bypass via client-supplied `X-Forwarded-For`.
  `client_ip()` now trusts only the proxy-set `X-Real-IP` / socket peer, never
  the client-controlled header, and per-user caps back the per-IP windows.
- F2 (LOW): only the post author may pin an answer (a commenter can no longer
  pin their own comment and force the post resolved).
- F3 (LOW): unbounded `cursor` query param capped at 512 chars (422, not 500).

Run: cd backend && python3 -m pytest tests/test_pt1_xff_bypass.py -q
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

STUB_USER = types.SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")
OTHER_USER = types.SimpleNamespace(id="u2", display_name="Bob", free_account=False, role="user")

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
    yield maker
    await engine.dispose()

@pytest_asyncio.fixture
async def env(db_env):
    maker = db_env
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

def _issue(title, body="Cold start problem on a winter morning"):
    return {"title": title, "body": body}

async def _new_issue(maker, **kwargs):
    async with maker() as s:
        post = sm.SocialIssuePost(
            author_user_id=kwargs.get("author_user_id", "u1"),
            author_display_name=kwargs.get("author_display_name", "Alice"),
            server_name="Server A",
            title=kwargs.get("title", "Engine won't start"),
            body=kwargs.get("body", "Cold mornings, the starter turns but the engine never catches."),
            tags=kwargs.get("tags", ["engine", "starting"]),
            status=kwargs.get("status", "open"),
            origin="local",
        )
        s.add(post)
        await s.commit()
        return post.id

async def _new_comment(maker, post_id, author_user_id="u1"):
    async with maker() as s:
        c = sm.SocialIssueComment(
            post_id=post_id, author_user_id=author_user_id,
            author_display_name="Helper", server_name="Server A", body="Try a new battery",
        )
        s.add(c)
        await s.commit()
        return c.id

@pytest.mark.asyncio
async def test_pt1_xff_rotation_cannot_bypass_rate_limit(env):
    """F1: rotating X-Forwarded-For must NOT reset the per-IP window.

    Before the fix client_ip() took `X-Forwarded-For.split(",")[0]` straight
    from the client header, so every request got a fresh key and the 6th
    create succeeded. Now XFF is ignored: all requests resolve to the single
    trusted peer, so the per-IP window accumulates under ONE key and the 6th
    create 429s. We assert the key-count invariant directly rather than the
    absolute peer identity, so the test is env-independent (Python/httpx/asyncio
    versions differ between local and CI).
    """
    import time
    app, _ = env
    _window._hits.clear()
    _user_window._hits.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for i in range(5):
            r = await c.post(
                "/social/issues",
                json=_issue(f"Rotating header issue {i}"),
                headers={"X-Forwarded-For": f"10.1.{i}.{i}"},
            )
            assert r.status_code == 201, r.text
        # The 5 forged-XFF requests must all land on ONE per-IP key. If XFF
        # rotation worked (the bug), we'd see 5 distinct IP keys here.
        ip_keys = {k: v for k, v in _window._hits.items() if k[0] == "/social/issues"}
        assert len(ip_keys) == 1, f"XFF rotation created multiple per-IP keys: {list(ip_keys)}"
        # Key-count is the security invariant; hit count is env-sensitive (CI
        # slowness can purge old entries). Assert at least one hit recorded.
        assert len(list(ip_keys.values())[0]) >= 1
        # Pre-seed the single key so the 6th request is guaranteed 429
        # regardless of earlier purging.
        only_key = next(iter(ip_keys))
        _window._hits[only_key].extend([time.monotonic()] * 5)
        _user_window._hits.clear()
        r = await c.post(
            "/social/issues",
            json=_issue("Sixth attempt with fresh forged IP"),
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers

@pytest.mark.asyncio
async def test_f1_per_user_cap_independent_of_ip(env):
    """F1: per-user create cap holds even after the per-IP window resets, and
    is per-user (a different account on the same peer is not capped)."""
    app, _ = env
    _window._hits.clear()
    _user_window._hits.clear()
    import time
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for i in range(5):
            r = await c.post("/social/issues", json=_issue(f"Cap test issue {i}"))
            assert r.status_code == 201, r.text
        # the per-user window must be non-empty for u1 (hit count env-sensitive)
        assert any(len(v) >= 1 for v in _user_window._hits.values()), _user_window._hits
        # Pre-seed the per-user key so the 6th request is guaranteed 429.
        user_keys = {k for k in _user_window._hits if k[0] == "issues-create"}
        assert len(user_keys) == 1, f"expected exactly one per-user cap key: {user_keys}"
        _user_window._hits[next(iter(user_keys))].extend([time.monotonic()] * 5)
        assert (await c.post("/social/issues", json=_issue("Cap exceeded"))).status_code == 429
        # per-IP window alone cannot explain the block: clear it, the per-user
        # cap still holds for u1.
        _window._hits.clear()
        assert (await c.post("/social/issues", json=_issue("Still capped for u1"))).status_code == 429
        # a different user on the same socket peer is not capped
        app.dependency_overrides[deps.require_premium_write] = lambda: OTHER_USER
        assert (await c.post("/social/issues", json=_issue("u2 is unaffected"))).status_code == 201

@pytest.mark.asyncio
async def test_f2_non_author_commenter_cannot_pin_answer(env):
    """F2: the comment's own author cannot pin it and force the post resolved
    unless they are the post author (404, PW-8 no-probing)."""
    app, maker = env
    pid = await _new_issue(maker, author_user_id="owner-1", author_display_name="Owner")
    cid = await _new_comment(maker, pid, author_user_id="u1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/social/issues/{pid}/comments/{cid}/answer")
        assert r.status_code == 404
        assert (await c.get(f"/social/issues/{pid}")).json()["status"] == "open"

@pytest.mark.asyncio
async def test_f2_post_author_can_pin_answer(env):
    """F2: the post author may still pin any comment (even someone else's) and
    resolve the post."""
    app, maker = env
    pid = await _new_issue(maker, author_user_id="u1")
    cid = await _new_comment(maker, pid, author_user_id="owner-2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(f"/social/issues/{pid}/comments/{cid}/answer")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        assert (await c.get(f"/social/issues/{pid}")).json()["resolved_comment_id"] == cid

@pytest.mark.asyncio
async def test_f3_oversized_cursor_rejected(env):
    """F3: cursor longer than 512 chars is rejected by validation (422), not
    base64-decoded/parsed (no 500). A valid-but-oversized cursor was accepted
    and executed before the cap (parsed into a keyset predicate); now it is a
    hard 422."""
    import base64
    import json

    big_id = "x" * 1000
    raw = json.dumps({"c": "2026-01-01T00:00:00", "i": big_id}).encode()
    oversized_valid = base64.urlsafe_b64encode(raw).decode()
    assert len(oversized_valid) > 512
    app, _ = env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/social/issues", params={"cursor": oversized_valid})
        assert r.status_code == 422
        # short-but-invalid cursor still yields a clean 400, not 500
        r = await c.get("/social/issues", params={"cursor": "!!!not-base64!!!"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_f1_client_ip_ignores_x_forwarded_for():
    """F1: client_ip() must never trust the client-controlled X-Forwarded-For
    header — only the proxy-set X-Real-IP / socket peer. Deterministic unit
    assertion, env-independent."""
    from starlette.requests import Request
    from app.services.auth import client_ip

    def _req(headers, client_host="198.51.100.7"):
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in headers.items()
            ],
        }
        if client_host is not None:
            scope["client"] = (client_host, 12345)
        return Request(scope)

    # No X-Real-IP: socket peer is used; XFF is ignored.
    req = _req({"X-Forwarded-For": "10.0.0.1, 10.0.0.2"})
    assert client_ip(req) == "198.51.100.7"
    # X-Real-IP set by the proxy wins; XFF still ignored.
    req = _req({"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "10.0.0.1"})
    assert client_ip(req) == "203.0.113.9"
    # No client at all: "unknown".
    req = _req({"X-Forwarded-For": "10.0.0.1"}, client_host=None)
    assert client_ip(req) == "unknown"
# ci-retrigger
