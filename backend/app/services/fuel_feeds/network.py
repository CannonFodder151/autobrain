"""Fuel Feeds — network boundary (single point, stubbed in tests)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

async def _fetch_json(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    if client is not None:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": settings.FUEL_INGEST_USER_AGENT}) as c:
        resp = await c.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()