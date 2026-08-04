"""Server version + GitHub release check."""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def current_version() -> str:
    return settings.APP_VERSION


async def check_latest_release() -> dict:
    """Query the GitHub releases API for the newest tag.

    Never raises: returns a conservative result when GitHub is unreachable.
    """
    url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        tag = data.get("tag_name") or ""
        version = tag.lstrip("v")
        return {
            "latest_version": version or tag,
            "release_name": data.get("name"),
            "published_at": data.get("published_at"),
            "html_url": data.get("html_url"),
            "up_to_date": _compare(current_version(), version) <= 0 if version else None,
            "reachable": True,
        }
    except Exception as exc:
        logger.warning("github_release_check_failed", error=str(exc))
        return {
            "latest_version": None,
            "release_name": None,
            "published_at": None,
            "html_url": None,
            "up_to_date": None,
            "reachable": False,
        }


def _compare(a: str, b: str) -> int:
    """Compare dotted versions. Returns <0 if a<b, 0 if equal, >0 if a>b."""
    import re

    def parts(v: str):
        return [int(x) for x in re.findall(r"\d+", v)]

    pa, pb = parts(a), parts(b)
    for x, y in zip(pa, pb):
        if x != y:
            return -1 if x < y else 1
    return (len(pa) > len(pb)) - (len(pa) < len(pb))
