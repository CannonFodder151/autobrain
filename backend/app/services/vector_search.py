"""Vector embedding service — generates and stores embeddings for searchable text."""

import json

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_EMBEDDING_DIM = settings.EMBEDDING_DIMENSION


def _to_text(entity_type: str, data: dict) -> str:
    """Extract searchable text from an entity dict."""
    if entity_type in ("diagnostic", "query"):
        parts = [data.get("symptoms", "")]
        ai_resp = data.get("ai_response")
        if isinstance(ai_resp, dict):
            parts.extend([
                ai_resp.get("summary", ""),
                json.dumps(ai_resp.get("items", [])),
            ])
        parts.extend([
            data.get("summary", ""),
            str(data.get("severity", "")),
        ])
        return " ".join(p for p in parts if p)

    if entity_type == "service":
        return " ".join(
            p for p in [
                data.get("description", ""),
                data.get("service_type", ""),
                data.get("notes", ""),
                data.get("workshop", ""),
                data.get("steps", ""),
            ]
            if p
        )

    if entity_type == "modification":
        return " ".join(
            p for p in [
                data.get("name", ""),
                data.get("category", ""),
                data.get("notes", ""),
                data.get("brand", ""),
            ]
            if p
        )

    if entity_type == "receipt":
        parts = [
            data.get("vendor", ""),
            data.get("original_name", ""),
        ]
        extracted = data.get("extracted")
        if isinstance(extracted, dict):
            for item in extracted.get("items", []):
                if isinstance(item, dict):
                    parts.append(item.get("name", ""))
                    parts.append(item.get("kind", ""))
        return " ".join(p for p in parts if p)

    return ""


async def _call_embedding_api(text: str) -> list[float] | None:
    """Get embedding from 9Router (OpenAI-compatible /embeddings endpoint)."""
    url = settings.AI_ROUTER_URL.rstrip("/")
    if not url or "your-9router-instance" in url:
        logger.info("embedding_router_disabled")
        return None

    api_key = settings.AI_ROUTER_API_KEY
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": settings.EMBEDDING_MODEL,
        "input": text[:8000],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{url}/embeddings",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as exc:
        logger.warning("embedding_api_failed", error=str(exc))
        return None


async def generate_embedding(entity_type: str, data: dict) -> list[float] | None:
    """Generate embedding vector for an entity. Returns None if router disabled."""
    text = _to_text(entity_type, data)
    if not text.strip():
        return None
    return await _call_embedding_api(text)
