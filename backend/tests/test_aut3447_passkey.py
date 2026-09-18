"""AUT-3447: WebAuthn passkey endpoint tests.

Covers:
- passkey registration begins for an authenticated user;
- passkey authentication begins for a valid user with stored passkeys;
- passkey list returns empty for new users;
- passkey delete removes a credential;
- authentication begin returns empty allowCredentials for unknown user;
- authentication begin fails without user_id or email query param;
- registration begin requires authentication;
- list requires authentication.

Runs on SQLite (no Postgres/Redis needed):
    DATABASE_URL=sqlite+aiosqlite:////tmp/aut3447.db pytest backend/tests/test_aut3447_passkey.py
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/aut3447-passkey.db"
os.environ["SECRET_KEY"] = "aut3447-test-secret"

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.passkey import PasskeyCredential  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _reinit_schema() -> None:
    asyncio.run(init_db())


async def _make_user(email: str = "passkey") -> User:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        u = User(
            email=f"{email}-{suffix}@example.com",
            display_name="Passkey Tester",
            hashed_password="$2b$12$placeholderhashplaceholderplaceholder",
            max_vehicles=1,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def _auth_header(user: User) -> dict:
    from app.services.auth import token_pair as tp

    async with SessionLocal() as db:
        fresh = await db.get(User, user.id)
        pair = tp(fresh)
        await db.commit()
    return {"Authorization": f"Bearer {pair.access_token}"}


async def _make_passkey(user: User, credential_id: str = "test-cred-id") -> PasskeyCredential:
    async with SessionLocal() as db:
        cred = PasskeyCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key="dGVzdC1wdWJsaWMta2V5",  # base64url("test-public-key")
            sign_count=0,
            device_type="platform",
            label="Test Passkey",
        )
        db.add(cred)
        await db.commit()
        await db.refresh(cred)
        return cred


# --- Tests ---


@pytest.mark.asyncio
async def test_register_begin_requires_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/register/begin",
            json={
                "rp_id": "localhost",
                "rp_name": "AutoBrain Test",
                "user_display_name": "Test User",
                "user_id": "dGVzdC11c2VyLWlk",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
            },
        )
        assert resp.status_code in (401, 422), f"Expected 401/422, got {resp.status_code}"


@pytest.mark.asyncio
async def test_register_begin_bad_rp_id() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/register/begin",
            headers=headers,
            json={
                "rp_id": "evil.com",
                "rp_name": "AutoBrain Test",
                "user_display_name": "Test User",
                "user_id": "dGVzdC11c2VyLWlk",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
            },
        )
        assert resp.status_code == 400
        assert "RP ID mismatch" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_empty_for_new_user() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/passkey/list",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "passkeys" in data
        assert len(data["passkeys"]) == 0


@pytest.mark.asyncio
async def test_list_with_passkey() -> None:
    user = await _make_user()
    await _make_passkey(user, credential_id="test-cred-123")
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/passkey/list",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["passkeys"]) == 1
        assert data["passkeys"][0]["credential_id"] == "test-cred-123"
        assert data["passkeys"][0]["label"] == "Test Passkey"
        assert data["passkeys"][0]["device_type"] == "platform"


@pytest.mark.asyncio
async def test_delete_passkey() -> None:
    user = await _make_user()
    cred = await _make_passkey(user, credential_id="to-delete-cred")
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/v1/auth/passkey/{cred.credential_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        # Verify it's gone
        resp2 = await client.get(
            "/api/v1/auth/passkey/list",
            headers=headers,
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["passkeys"]) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_passkey() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            "/api/v1/auth/passkey/nonexistent-cred-id",
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_begin_requires_user_id_or_email() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/authenticate/begin",
            json={
                "rp_id": "localhost",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
                "allow_credentials": [],
            },
        )
        assert resp.status_code == 400
        assert "user_id" in resp.json()["detail"] or "email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_begin_unknown_user_returns_empty_allow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/authenticate/begin?user_id=nonexistent",
            json={
                "rp_id": "localhost",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
                "allow_credentials": [],
            },
        )
        # Should return 200 with empty allowCredentials (don't reveal account existence)
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        assert "allowCredentials" in data["options"]
        assert len(data["options"]["allowCredentials"]) == 0


@pytest.mark.asyncio
async def test_auth_begin_valid_user_with_passkeys() -> None:
    user = await _make_user()
    await _make_passkey(user, credential_id="auth-cred-1")
    await _make_passkey(user, credential_id="auth-cred-2")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/auth/passkey/authenticate/begin?user_id={user.id}",
            json={
                "rp_id": "localhost",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
                "allow_credentials": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        assert "allowCredentials" in data["options"]
        assert len(data["options"]["allowCredentials"]) == 2


@pytest.mark.asyncio
async def test_auth_begin_by_email() -> None:
    user = await _make_user()
    await _make_passkey(user, credential_id="email-cred-1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/auth/passkey/authenticate/begin?email={user.email}",
            json={
                "rp_id": "localhost",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
                "allow_credentials": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["options"]["allowCredentials"]) == 1


@pytest.mark.asyncio
async def test_auth_complete_requires_request_id() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/authenticate/complete",
            json={
                "credential": {
                    "id": "test-cred-id",
                    "rawId": "test-cred-id",
                    "response": {
                        "clientDataJSON": "dGVzdA",
                        "authenticatorData": "dGVzdA",
                        "signature": "dGVzdA",
                    },
                    "type": "public-key",
                },
            },
        )
        # Missing request_id in payload
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_auth_complete_bad_credential_id() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/authenticate/complete",
            headers=headers,
            json={
                "credential": {
                    "id": "nonexistent-cred",
                    "rawId": "nonexistent-cred",
                    "response": {
                        "clientDataJSON": "dGVzdA",
                        "authenticatorData": "dGVzdA",
                        "signature": "dGVzdA",
                    },
                    "type": "public-key",
                },
                "request_id": "fake-request-id",
            },
        )
        assert resp.status_code == 401
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_complete_requires_request_id() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/register/complete",
            headers=headers,
            json={
                "credential": {
                    "id": "test-cred-id",
                    "rawId": "test-cred-id",
                    "response": {
                        "clientDataJSON": "dGVzdA",
                        "attestationObject": "dGVzdA",
                    },
                    "type": "public-key",
                },
            },
        )
        # Missing request_id in payload
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_complete_bad_request_id() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/register/complete",
            headers=headers,
            json={
                "credential": {
                    "id": "test-cred-id",
                    "rawId": "test-cred-id",
                    "response": {
                        "clientDataJSON": "dGVzdA",
                        "attestationObject": "dGVzdA",
                    },
                    "type": "public-key",
                },
                "request_id": "expired-or-fake",
            },
        )
        assert resp.status_code == 400
        assert "session" in resp.json()["detail"].lower() or "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_begin_returns_options() -> None:
    user = await _make_user()
    headers = await _auth_header(user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/passkey/register/begin",
            headers=headers,
            json={
                "rp_id": "localhost",
                "rp_name": "AutoBrain Test",
                "user_display_name": "Test User",
                "user_id": "dGVzdC11c2VyLWlk",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "options" in data
        assert "request_id" in data
        assert "rp" in data["options"]
        assert "user" in data["options"]
        assert "challenge" in data["options"]
        assert "pubKeyCredParams" in data["options"]
        assert isinstance(data["options"]["pubKeyCredParams"], list)
        assert len(data["options"]["pubKeyCredParams"]) > 0


@pytest.mark.asyncio
async def test_auth_complete_invalid_response() -> None:
    user = await _make_user()
    cred = await _make_passkey(user, credential_id="invalid-resp-cred")
    transport = ASGITransport(app=app)

    # First get options
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        begin_resp = await client.post(
            f"/api/v1/auth/passkey/authenticate/begin?user_id={user.id}",
            json={
                "rp_id": "localhost",
                "challenge": "dGVzdC1jaGFsbGVuZ2UtdmFsdWU",
                "allow_credentials": [],
            },
        )
        request_id = begin_resp.json()["request_id"]

        # Try to complete with garbage response
        resp = await client.post(
            "/api/v1/auth/passkey/authenticate/complete",
            json={
                "credential": {
                    "id": cred.credential_id,
                    "rawId": cred.credential_id,
                    "response": {
                        "clientDataJSON": "dGVzdA",
                        "authenticatorData": "dGVzdA",
                        "signature": "dGVzdA",
                    },
                    "type": "public-key",
                },
                "request_id": request_id,
            },
        )
        # Should fail verification (garbage data)
        assert resp.status_code == 400
