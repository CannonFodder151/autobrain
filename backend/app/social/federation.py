"""Federation hub client matching the hub service contract (AUT-333).

The hub itself lives in the private repo `autobrain-federation-hub` (AUT-333). This module is
the origin-server side: keypair + registration, signed outbox pushes and inbox
pulls. Every call is resilient — hub failures are logged and never break the
local feed (AUT-294 §4 / req 15).
"""

import base64
import hashlib
import json
import secrets
import time

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.social.models import SocialServerConfig

logger = get_logger(__name__)

_TIMEOUT = 10.0


class FederationUnavailable(RuntimeError):
    pass


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    return f"{method}\n{path}\n{timestamp}\n{nonce}\n{_sha256_hex(body)}".encode()


def _sign(private_key_hex: str, canonical: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return base64.b64encode(priv.sign(canonical)).decode()


def generate_keypair() -> tuple[str, str]:
    """Generate (private_key_hex, public_key_hex) — the Ed25519 pair a server
    registers with the hub for signed-request authentication."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    private_hex = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_hex = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private_hex, public_hex


def _hub_url(cfg: SocialServerConfig) -> str:
    url = cfg.server_hub_url or settings.SOCIAL_FEDERATION_HUB_URL
    if not url:
        raise FederationUnavailable("hub not configured")
    return url.rstrip("/")


def _headers(cfg: SocialServerConfig, method: str, path: str, body: bytes) -> dict[str, str]:
    if not (cfg.hub_server_id and cfg.hub_api_key and cfg.hub_private_key):
        raise FederationUnavailable("server not registered with the hub")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    canonical = _canonical(method, path, timestamp, nonce, body)
    return {
        "Content-Type": "application/json",
        "X-Server-Id": cfg.hub_server_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": _sign(cfg.hub_private_key, canonical),
        "X-Api-Key": cfg.hub_api_key,
    }


async def _post(cfg: SocialServerConfig, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    headers = _headers(cfg, "POST", path, body)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(_hub_url(cfg) + path, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {path} -> {resp.status_code}")
    return resp.json()


async def _get(cfg: SocialServerConfig, path: str, params: dict | None = None) -> dict:
    headers = _headers(cfg, "GET", path, b"")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(_hub_url(cfg) + path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {path} -> {resp.status_code}")
    return resp.json()


async def get_server_status(cfg: SocialServerConfig) -> dict:
    """Public hub status for this server (AUT-731): lets the client detect when
    the hub operator has approved a `pending` registration (AUT-525) without
    re-registering. No auth needed — the hub exposes GET /v1/server/{id}."""
    if not cfg.hub_server_id:
        raise FederationUnavailable("server not registered with the hub")
    url = _hub_url(cfg) + f"/v1/server/{cfg.hub_server_id}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {url} -> {resp.status_code}")
    return resp.json()


async def register(
    cfg: SocialServerConfig,
    server_name: str,
    server_email: str,
    public_key_hex: str,
) -> dict:
    """Register this server with the hub. Returns {server_id, api_key,
    status, license_status, checkout_url}."""
    path = "/v1/register"
    payload = {
        "server_name": server_name,
        "email": server_email,
        "public_key": public_key_hex,
        "hosted": bool(settings.SOCIAL_FEDERATION_HOSTED),
        "registration_key": settings.SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY,
    }
    body = json.dumps(payload).encode()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(
                _hub_url(cfg) + path, content=body, headers={"Content-Type": "application/json"}
            )
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {path} -> {resp.status_code}")
    return resp.json()


async def push_outbox(cfg: SocialServerConfig, build_id: str, payload: dict) -> None:
    """Push a locally-created build (metadata + photo URLs) to the hub."""
    await _post(cfg, "/v1/outbox", {"build_id": build_id, "build": payload})


async def push_event(cfg: SocialServerConfig, build_id: str, event_type: str, payload: dict) -> None:
    """Fan a comment/like event out so remote copies of a build stay in sync.

    `build_id` is the id on the event's origin server; receiving servers match
    it to their local id or remote_build_id.
    """
    await _post(cfg, "/v1/events", {
        "event_type": event_type,
        "payload": {"build_id": build_id, **payload},
    })


async def pull_inbox(cfg: SocialServerConfig) -> list[dict]:
    """Fetch remote builds the hub routes to this server."""
    data = await _get(cfg, "/v1/inbox")
    return data.get("builds", []) if isinstance(data, dict) else []


async def pull_events(cfg: SocialServerConfig, after: int) -> dict:
    """Pull comment/like events for this server, resuming from the cursor."""
    data = await _get(cfg, "/v1/events", params={"after": after})
    return data if isinstance(data, dict) else {}
