"""Federation hub client (AUT-294 §4).

The hub itself is a separate service (Deployment Lead's workstream). This
module is the origin-server side: register, push outbox, pull inbox. Every call
is resilient — hub failures are logged and never break the local feed.
"""

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.social.models import SocialServerConfig

logger = get_logger(__name__)

_TIMEOUT = 10.0


class FederationUnavailable(RuntimeError):
    pass


def _headers(cfg: SocialServerConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg.hub_server_id:
        headers["X-Server-Id"] = cfg.hub_server_id
    if cfg.hub_api_key:
        headers["X-API-Key"] = cfg.hub_api_key
    return headers


def _hub_url(cfg: SocialServerConfig) -> str:
    url = cfg.server_hub_url or settings.SOCIAL_FEDERATION_HUB_URL
    if not url:
        raise FederationUnavailable("hub not configured")
    return url.rstrip("/")


async def _post(cfg: SocialServerConfig, path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(_hub_url(cfg) + path, json=payload, headers=_headers(cfg))
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {path} -> {resp.status_code}")
    return resp.json()


async def _get(cfg: SocialServerConfig, path: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(_hub_url(cfg) + path, headers=_headers(cfg))
        except httpx.HTTPError as exc:
            raise FederationUnavailable(str(exc)) from exc
    if resp.status_code >= 300:
        raise FederationUnavailable(f"hub {path} -> {resp.status_code}")
    return resp.json()


async def register(cfg: SocialServerConfig, server_name: str, server_email: str) -> dict:
    """Register this server with the hub. Returns {server_id, api_key}."""
    return await _post(cfg, "/v1/register", {"server_name": server_name, "server_email": server_email})


async def push_outbox(cfg: SocialServerConfig, build_id: str, payload: dict) -> None:
    """Push a locally-created build (metadata + photo URLs) to the hub."""
    await _post(cfg, "/v1/outbox", {"build_id": build_id, "build": payload})


async def pull_inbox(cfg: SocialServerConfig) -> list[dict]:
    """Fetch remote builds the hub routes to this server."""
    data = await _get(cfg, "/v1/inbox")
    return data.get("builds", []) if isinstance(data, dict) else []
