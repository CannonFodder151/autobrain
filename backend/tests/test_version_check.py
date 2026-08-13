"""AUT-346: server version banner must not claim "Up to date" when behind."""

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./t.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402

from app.services.version import _compare, check_latest_release, check_mobile_latest_release  # noqa: E402


class _FakeResp:
    def __init__(self, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, _FakeResp], headers: dict | None = None) -> None:
        self._responses = responses
        self.headers = headers or {}

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str, **kwargs) -> _FakeResp:
        return self._responses[url]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("0.3.6", "0.3.10", -1),
        ("0.3.10", "0.3.6", 1),
        ("0.3.10", "0.3.10", 0),
        ("0.3.12", "0.3.10", 1),
        ("0.3.10", "0.3.12", -1),
    ],
)
def test_compare_dotted_versions(a: str, b: str, expected: int) -> None:
    assert _compare(a, b) == expected


def test_uptodate_true_when_running_behind_repo(monkeypatch) -> None:
    # No releases published → falls back to main's pubspec version (0.3.10)
    # while the running server reports 0.3.6. That is NOT up to date.
    monkeypatch.setattr(
        "app.services.version.current_version", lambda: "0.3.6"
    )
    client = _FakeClient(
        {
            "https://api.github.com/repos/CannonFodder151/autobrain/releases/latest": _FakeResp(
                404
            ),
            "https://api.github.com/repos/CannonFodder151/autobrain/commits/main": _FakeResp(
                payload={"sha": "abc", "commit": {"message": "x"}}
            ),
            "https://raw.githubusercontent.com/CannonFodder151/autobrain/main/frontend/pubspec.yaml": _FakeResp(
                text="version: 0.3.10+15"
            ),
        }
    )
    monkeypatch.setattr("app.services.version.httpx.AsyncClient", lambda **_: client)

    result = asyncio.run(check_latest_release())
    assert result["up_to_date"] is False
    assert result["repo_version"] == "0.3.10"


def test_uptodate_true_when_matching_repo(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.version.current_version", lambda: "0.3.10"
    )
    client = _FakeClient(
        {
            "https://api.github.com/repos/CannonFodder151/autobrain/releases/latest": _FakeResp(
                404
            ),
            "https://api.github.com/repos/CannonFodder151/autobrain/commits/main": _FakeResp(
                payload={"sha": "abc", "commit": {"message": "x"}}
            ),
            "https://raw.githubusercontent.com/CannonFodder151/autobrain/main/frontend/pubspec.yaml": _FakeResp(
                text="version: 0.3.10+15"
            ),
        }
    )
    monkeypatch.setattr("app.services.version.httpx.AsyncClient", lambda **_: client)

    result = asyncio.run(check_latest_release())
    assert result["up_to_date"] is True
    assert result["repo_version"] == "0.3.10"


def test_public_repo_check_never_sends_token(monkeypatch) -> None:
    """AUT-442: GITHUB_TOKEN must NOT be sent on public autobrain requests."""
    monkeypatch.setattr("app.services.version.settings.GITHUB_TOKEN", "ghp_secret")
    client = _FakeClient(
        {
            "https://api.github.com/repos/CannonFodder151/autobrain/releases/latest": _FakeResp(
                404
            ),
            "https://api.github.com/repos/CannonFodder151/autobrain/commits/main": _FakeResp(
                payload={"sha": "abc", "commit": {"message": "x"}}
            ),
            "https://raw.githubusercontent.com/CannonFodder151/autobrain/main/frontend/pubspec.yaml": _FakeResp(
                text="version: 0.3.10+15"
            ),
        }
    )

    def _ctor(**kwargs):
        client.headers = kwargs.get("headers") or {}
        return client

    monkeypatch.setattr("app.services.version.httpx.AsyncClient", _ctor)

    asyncio.run(check_latest_release())

    assert "Authorization" not in client.headers
    assert "ghp_secret" not in str(client.headers)


def test_mobile_repo_check_requires_token(monkeypatch) -> None:
    """AUT-442: private mobile repo check still authenticates with the token."""
    monkeypatch.setattr("app.services.version.settings.GITHUB_TOKEN", "ghp_secret")
    client = _FakeClient(
        {
            "https://api.github.com/repos/CannonFodder151/autobrain-mobile/releases/latest": _FakeResp(
                payload={
                    "tag_name": "v1.2.3",
                    "html_url": "https://github.com/CannonFodder151/autobrain-mobile/releases/tag/v1.2.3",
                    "published_at": "2026-01-01T00:00:00Z",
                }
            )
        }
    )
    def _ctor(**kwargs):
        client.headers = kwargs.get("headers") or {}
        return client

    monkeypatch.setattr("app.services.version.httpx.AsyncClient", _ctor)

    result = asyncio.run(check_mobile_latest_release())

    assert result["latest_version"] == "1.2.3"
    assert client.headers.get("Authorization") == "Bearer ghp_secret"