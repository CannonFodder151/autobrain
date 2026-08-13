"""Server version + GitHub update check.

Compares the running server against GitHub:
  1. A published release tag if one exists, otherwise
  2. the latest commit on main and the version string in the repo's
     frontend/pubspec.yaml.

Never raises: returns a conservative result when GitHub is unreachable.
"""

import re

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def current_version() -> str:
    return settings.APP_VERSION


async def check_mobile_latest_release() -> dict:
    """Latest published mobile-app release from GitHub.

    The mobile repo (`CannonFodder151/autobrain-mobile`) is private, so this
    must be read server-side with GITHUB_TOKEN and proxied to the app. Unlike
    `check_latest_release`, there is no `up_to_date` comparison here: the app
    compares the tag against its own installed version. Never raises.
    """
    result: dict = {"reachable": True, "latest_version": None, "html_url": None}
    try:
        async with httpx.AsyncClient(timeout=12, headers=_headers(authenticated=True)) as client:
            release = await _get(
                client,
                f"https://api.github.com/repos/{settings.MOBILE_GITHUB_REPO}/releases/latest",
            )
            if release:
                tag = (release.get("tag_name") or "").lstrip("v")
                result["latest_version"] = tag or release.get("tag_name")
                result["html_url"] = release.get("html_url")
                result["published_at"] = release.get("published_at")
                return result
            # GitHub reachable but no published release yet.
            result["latest_version"] = None
            return result
    except Exception as exc:
        logger.warning("github_mobile_check_failed", error=str(exc))
        return {"latest_version": None, "html_url": None, "reachable": False}


def _headers(authenticated: bool = False) -> dict:
    """Default headers for GitHub requests.

    `authenticated=True` is used ONLY for the private mobile repo. Public-repo
    checks (`autobrain`) never send the token — GitHub's unauthenticated API
    allows 60 requests/hour per IP, plenty for admin-page version checks.
    Keeping the PAT off public requests shrinks the exposure surface in case
    of a leak.
    """
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "autobrain"}
    if authenticated and settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


async def check_latest_release() -> dict:
    result: dict = {"reachable": True, "up_to_date": None}
    try:
        async with httpx.AsyncClient(timeout=12, headers=_headers()) as client:
            # 1) A published release (best signal for versioned deploys).
            release = await _get(client, f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases/latest")
            if release:
                tag = (release.get("tag_name") or "").lstrip("v")
                result["latest_version"] = tag or release.get("tag_name")
                result["release_name"] = release.get("name")
                result["published_at"] = release.get("published_at")
                result["html_url"] = release.get("html_url")
                if tag:
                    result["up_to_date"] = _compare(current_version(), tag) >= 0
                return result

            # 2) No releases yet — fall back to the latest commit on main.
            commit = await _get(client, f"https://api.github.com/repos/{settings.GITHUB_REPO}/commits/main")
            if commit:
                sha = commit.get("sha", "")
                result["latest_version"] = sha[:12] if sha else None
                result["release_name"] = None
                result["published_at"] = (commit.get("commit", {}) or {}).get("committer", {}).get("date")
                result["html_url"] = commit.get("html_url")
                result["commit_message"] = (commit.get("commit", {}) or {}).get("message", "").split("\n")[0]

                # 3) Version published in the repo's pubspec.
                pubspec = await _get_raw(client, f"https://raw.githubusercontent.com/{settings.GITHUB_REPO}/main/frontend/pubspec.yaml")
                repo_version = _pubspec_version(pubspec)
                if repo_version:
                    result["repo_version"] = repo_version
                    result["up_to_date"] = _compare(current_version(), repo_version) >= 0
                return result

            # GitHub reachable but neither releases nor commits found.
            result["latest_version"] = None
            return result
    except Exception as exc:
        logger.warning("github_version_check_failed", error=str(exc))
        return {
            "latest_version": None,
            "release_name": None,
            "published_at": None,
            "html_url": None,
            "up_to_date": None,
            "reachable": False,
        }


async def _get(client: httpx.AsyncClient, url: str):
    resp = await client.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def _get_raw(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _pubspec_version(text: str) -> str | None:
    m = re.search(r"^version:\s*([^\s#]+)", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().split("+")[0]  # drop +build suffix


def _compare(a: str, b: str) -> int:
    """Compare dotted versions. Returns <0 if a<b, 0 if equal, >0 if a>b."""
    def parts(v: str):
        return [int(x) for x in re.findall(r"\d+", v)]

    pa, pb = parts(a), parts(b)
    for x, y in zip(pa, pb):
        if x != y:
            return -1 if x < y else 1
    return (len(pa) > len(pb)) - (len(pa) < len(pb))
