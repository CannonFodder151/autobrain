"""AUT-207: token lifecycle hardening — refresh rotation/revocation + access TTL.

Covers:
- access tokens carry a `ver` = user.token_version at issue time;
- refreshing rotates the refresh token (old one is denylisted, replay rejected);
- logout bumps token_version, instantly invalidating outstanding tokens;
- password change bumps token_version, invalidating outstanding tokens;
- get_current_user rejects an access token minted before a version bump.

Runs on SQLite (no Postgres/Redis needed):
    DATABASE_URL=sqlite+aiosqlite:////tmp/aut207.db pytest backend/tests/test_aut207_token_lifecycle.py
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/aut207-token-lifecycle.db"
os.environ["SECRET_KEY"] = "aut207-test-secret"

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, create_password_reset_token  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.refresh_token import RevokedRefreshToken  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _reinit_schema() -> None:
    asyncio.run(init_db())


async def _make_user(email: str = "tok") -> User:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        u = User(
            email=f"{email}-{suffix}@example.com",
            display_name="Owner",
            hashed_password="$2b$12$placeholderhashplaceholderplaceholder",
            max_vehicles=3,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def _login(user: User) -> dict:
    from app.api.v1.auth import _token_pair

    async with SessionLocal() as db:
        fresh = await db.get(User, user.id)
        pair = _token_pair(fresh)
        await db.commit()
    return {"access": pair.access_token, "refresh": pair.refresh_token}


async def _refresh(refresh: str) -> tuple[int, dict | None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        body = resp.json() if resp.status_code == 200 else None
        return resp.status_code, body


async def _me(access: str) -> int:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        return resp.status_code


@pytest.mark.asyncio
async def test_access_token_carries_ver() -> None:
    from jose import jwt as jose_jwt

    from app.core.config import settings

    payload = jose_jwt.decode(
        create_access_token("user-x", token_version=3),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    assert payload["type"] == "access"
    assert payload["ver"] == 3


@pytest.mark.asyncio
async def test_refresh_token_carries_jti_and_ver() -> None:
    from jose import jwt as jose_jwt

    from app.core.config import settings
    from app.core.security import create_refresh_token

    payload = jose_jwt.decode(
        create_refresh_token("user-x", token_version=3),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    assert payload["type"] == "refresh"
    assert payload["ver"] == 3
    assert payload["jti"]


@pytest.mark.asyncio
async def test_refresh_rotates_and_denylists_old() -> None:
    user = await _make_user()
    pair = await _login(user)

    code, body = await _refresh(pair["refresh"])
    assert code == 200, body
    assert body["refresh_token"] != pair["refresh"]

    # Replaying the OLD refresh token is rejected (denylisted on rotation).
    code2, _ = await _refresh(pair["refresh"])
    assert code2 == 401


@pytest.mark.asyncio
async def test_denylist_row_written() -> None:
    from jose import jwt as jose_jwt

    from app.core.config import settings

    user = await _make_user()
    pair = await _login(user)
    old_payload = jose_jwt.decode(
        pair["refresh"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    await _refresh(pair["refresh"])
    async with SessionLocal() as db:
        assert await db.get(RevokedRefreshToken, old_payload["jti"]) is not None


@pytest.mark.asyncio
async def test_logout_revokes_all_tokens() -> None:
    user = await _make_user()
    pair = await _login(user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": pair["refresh"]}
        )
        assert resp.status_code == 200, resp.text

    assert await _me(pair["access"]) == 401
    code, _ = await _refresh(pair["refresh"])
    assert code == 401


@pytest.mark.asyncio
async def test_relogin_after_logout_works() -> None:
    user = await _make_user()
    pair = await _login(user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/auth/logout", json={"refresh_token": pair["refresh"]}
        )
    pair2 = await _login(user)
    assert await _me(pair2["access"]) == 200
    code, _ = await _refresh(pair2["refresh"])
    assert code == 200


@pytest.mark.asyncio
async def test_password_change_revokes_tokens() -> None:
    user = await _make_user()
    pair = await _login(user)
    reset = create_password_reset_token(user.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": reset, "new_password": "newpassword123"},
        )
        assert resp.status_code == 200, resp.text

    assert await _me(pair["access"]) == 401
    code, _ = await _refresh(pair["refresh"])
    assert code == 401


@pytest.mark.asyncio
async def test_version_bump_rejects_stale_access_token() -> None:
    user = await _make_user()
    stale = create_access_token(user.id, token_version=0)
    assert await _me(stale) == 200  # valid before bump

    async with SessionLocal() as db:
        u = await db.get(User, user.id)
        u.token_version += 1
        await db.commit()

    assert await _me(stale) == 401
