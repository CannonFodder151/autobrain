"""Issues Blog federation regression tests (AUT-756).

Guards the cross-instance path that was cut to local-only in v1 (AUT-666) and
is now implemented mirroring the build path:
  - creating an issue pushes a `type: "issue"` outbox entry to the hub
  - the feed/issue sync loop routes `type: "issue"` inbox items into
    SocialIssuePost (origin="remote", origin photo URLs preserved)
  - comment events fan out and are applied on the remote side
  - answer events resolve the remote copy (matched by origin comment id)

Self-contained: own sqlite engine + dependency overrides; the federation
client and MinIO are stubbed. Run: cd backend && python3 -m pytest tests/test_issues_federation.py -q
"""

import os
import types

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

import pytest
import pytest_asyncio
from app.api import deps
from app.api.v1 import issues as issues_api
from app.api.v1 import social as social_api
from app.db.session import Base, get_db
from app.social import federation
from app.social import models as sm
from app.social.rate_limit import _window
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

STUB_USER = types.SimpleNamespace(id="u1", display_name="Alice", free_account=False, role="user")


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
async def session(db_env):
    maker, _ = db_env
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def issues_app(db_env, monkeypatch):
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
    monkeypatch.setattr("app.workers.tasks.queue_embedding", lambda *a, **k: None)
    _window._hits.clear()
    yield app


def _noop(*a, **k):
    return None


@pytest.mark.asyncio
async def test_create_issue_pushes_issue_outbox(issues_app, db_env, monkeypatch):
    """POST /social/issues fans the post out to the hub with type=issue."""
    pushed = {}

    async def _capture_push(cfg, build_id, payload):
        pushed["build_id"] = build_id
        pushed["payload"] = payload

    monkeypatch.setattr(federation, "push_outbox", _capture_push)
    async with AsyncClient(transport=ASGITransport(app=issues_app), base_url="http://test") as c:
        r = await c.post("/social/issues", json={
            "title": "Engine won't start",
            "body": "It cranks but does not fire.",
        })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["origin"] == "local"
    assert pushed
    assert pushed["build_id"] == data["id"]
    payload = pushed["payload"]
    assert payload["type"] == "issue"
    assert payload["post_id"] == data["id"]
    assert payload["title"] == "Engine won't start"
    assert payload["author_display_name"] == "Alice"
    assert payload["server_name"] == "Server A"
    assert "photo_urls" in payload


@pytest.mark.asyncio
async def test_create_issue_without_federation_does_not_push(db_env, monkeypatch):
    """Local-only servers never touch the hub."""
    maker, _ = db_env
    async with maker() as s:
        cfg = await s.get(sm.SocialServerConfig, 1)
        cfg.federation_enabled = False
        await s.commit()

    app = FastAPI()
    app.include_router(issues_api.router)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[deps.require_premium] = lambda: STUB_USER
    app.dependency_overrides[deps.require_premium_write] = lambda: STUB_USER
    app.dependency_overrides[social_api.require_social_feature] = lambda: None
    monkeypatch.setattr("app.workers.tasks.queue_embedding", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(federation, "push_outbox", lambda *a, **k: calls.append(a))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/social/issues", json={"title": "T", "body": "B"})
    assert r.status_code == 201, r.text
    assert calls == []

    async with maker() as s:
        cfg = await s.get(sm.SocialServerConfig, 1)
        cfg.federation_enabled = True
        await s.commit()


@pytest.mark.asyncio
async def test_pull_remote_issue_inserts_remote_post(session):
    """Inbox items tagged type=issue become origin=remote blog posts."""
    from app.api.v1.issues import pull_remote_issue

    item = {"origin_server": "srv-b", "build": {
        "type": "issue",
        "post_id": "issue-1",
        "title": "Remote problem",
        "body": "Remote details",
        "author_display_name": "Bob",
        "server_name": "Server B",
        "vehicle_snapshot": {"make": "Honda", "model": "CBR500R", "year": 2023},
        "tags": ["electrical"],
        "created_at": "2026-08-15T00:00:00+00:00",
        "photo_urls": ["https://origin.example/p1.webp"],
    }}
    await pull_remote_issue(session, item, item["build"])
    await session.commit()

    post = (await session.scalars(
        select(sm.SocialIssuePost).where(sm.SocialIssuePost.remote_post_id == "issue-1")
    )).one()
    assert post.origin == "remote"
    assert post.author_display_name == "Bob"
    assert post.remote_server_id == "srv-b"
    assert post.status_hidden is False
    import json
    assert json.loads(post.photo_urls_json) == ["https://origin.example/p1.webp"]

    # Dedupe: pulling the same item again adds nothing.
    await pull_remote_issue(session, item, item["build"])
    count = len((await session.scalars(
        select(sm.SocialIssuePost).where(sm.SocialIssuePost.remote_post_id == "issue-1")
    )).all())
    assert count == 1


@pytest.mark.asyncio
async def test_apply_issue_comment_event(session):
    """A remote comment event lands on the matching local copy."""
    from app.api.v1.issues import apply_issue_event, pull_remote_issue

    item = {"origin_server": "srv-b", "build": {
        "type": "issue", "post_id": "issue-2", "title": "T", "body": "B",
        "author_display_name": "Bob", "server_name": "Server B",
    }}
    await pull_remote_issue(session, item, item["build"])
    await session.commit()
    post = (await session.scalars(
        select(sm.SocialIssuePost).where(sm.SocialIssuePost.remote_post_id == "issue-2")
    )).one()

    await apply_issue_event(session, {
        "event_type": "comment",
        "payload": {
            "build_id": "issue-2",
            "post_type": "issue",
            "comment_id": "c-1",
            "author_display_name": "Carol",
            "server_name": "Server C",
            "body": "Try the relay.",
            "is_answer": False,
        },
    })
    await session.commit()
    comment = (await session.scalars(
        select(sm.SocialIssueComment).where(sm.SocialIssueComment.post_id == post.id)
    )).one()
    assert comment.remote_comment_id == "c-1"
    assert comment.body == "Try the relay."
    assert comment.is_answer is False

    # Duplicate event is ignored.
    await apply_issue_event(session, {
        "event_type": "comment",
        "payload": {
            "build_id": "issue-2", "post_type": "issue", "comment_id": "c-1",
            "author_display_name": "Carol", "server_name": "Server C", "body": "Try the relay.",
        },
    })
    count = len((await session.scalars(
        select(sm.SocialIssueComment).where(sm.SocialIssueComment.post_id == post.id)
    )).all())
    assert count == 1


@pytest.mark.asyncio
async def test_apply_issue_answer_event_resolves(session):
    """Answer events resolve the remote copy and pin the matching comment."""
    from app.api.v1.issues import apply_issue_event, pull_remote_issue

    item = {"origin_server": "srv-b", "build": {
        "type": "issue", "post_id": "issue-3", "title": "T", "body": "B",
        "author_display_name": "Bob", "server_name": "Server B",
    }}
    await pull_remote_issue(session, item, item["build"])
    await session.commit()
    post = (await session.scalars(
        select(sm.SocialIssuePost).where(sm.SocialIssuePost.remote_post_id == "issue-3")
    )).one()

    await apply_issue_event(session, {
        "event_type": "comment",
        "payload": {
            "build_id": "issue-3", "post_type": "issue", "comment_id": "c-2",
            "author_display_name": "Carol", "server_name": "Server C",
            "body": "Fixed it.", "is_answer": False,
        },
    })
    await apply_issue_event(session, {
        "event_type": "comment",
        "payload": {
            "build_id": "issue-3", "post_type": "issue", "comment_id": "c-2",
            "author_display_name": "Carol", "server_name": "Server C",
            "body": "Fixed it.", "is_answer": True,
        },
    })
    await session.commit()
    comment = (await session.scalars(
        select(sm.SocialIssueComment).where(sm.SocialIssueComment.post_id == post.id)
    )).one()
    assert comment.is_answer is True
    assert post.status == "resolved"
    assert post.resolved_comment_id == comment.id


@pytest.mark.asyncio
async def test_sync_federation_routes_issue_and_build(db_env, session, monkeypatch):
    """The feed sync loop inserts both build and issue inbox items."""
    from app.api.v1.social import _sync_federation

    async def _builds(cfg):
        return [
            {"origin_server": "srv-b", "build": {
                "type": "issue", "post_id": "issue-4", "title": "Blog",
                "body": "Details", "author_display_name": "Bob", "server_name": "Server B",
            }},
            {"origin_server": "srv-b", "build": {
                "build_id": "build-1", "title": "My build", "caption": "Cap",
                "author_display_name": "Bob", "server_name": "Server B",
            }},
        ]

    async def _events(cfg, after):
        return {"events": [], "next_cursor": after}

    monkeypatch.setattr(federation, "pull_inbox", _builds)
    monkeypatch.setattr(federation, "pull_events", _events)

    cfg = await session.get(sm.SocialServerConfig, 1)
    cfg.last_inbox_sync = None
    cfg.last_event_sync = 0
    await session.commit()

    await _sync_federation(session)

    issue = (await session.scalars(
        select(sm.SocialIssuePost).where(sm.SocialIssuePost.remote_post_id == "issue-4")
    )).one()
    assert issue.origin == "remote"
    assert issue.title == "Blog"
    build = (await session.scalars(
        select(sm.SocialBuild).where(sm.SocialBuild.remote_build_id == "build-1")
    )).one()
    assert build.title == "My build"
