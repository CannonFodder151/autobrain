"""AUT-532 regression guards.

Registering the server with the federation hub returned 502 "Hub unreachable:
hub not configured" because none of the compose files wired
SOCIAL_FEDERATION_HUB_URL into the backend service. These guards keep that
wiring in place and document the error mapping for the unconfigured case.
"""

from pathlib import Path

import pytest

from app.core import config as config_module
from app.social import federation
from app.social.models import SocialServerConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

# (compose file, backend image marker that scopes the check, expected env lines)
COMPOSE_BACKEND_ENV = [
    (
        "docker-compose.hosted.yml",
        "cannonfodder151/autobrain-backend:hosted",
        [
            "SOCIAL_FEDERATION_HUB_URL: ${SOCIAL_FEDERATION_HUB_URL:-https://hub.autobrainservice.app}",
            'SOCIAL_FEDERATION_HOSTED: "true"',
        ],
    ),
    (
        "docker-compose.prod.yml",
        "x-backend-base: &backend-base",
        [
            "SOCIAL_FEDERATION_HUB_URL: ${SOCIAL_FEDERATION_HUB_URL:-https://hub.autobrainservice.app}",
            "SOCIAL_FEDERATION_HOSTED: ${SOCIAL_FEDERATION_HOSTED:-false}",
        ],
    ),
    (
        "docker-compose.yml",
        "x-backend-base: &backend-base",
        [
            "SOCIAL_FEDERATION_HUB_URL: ${SOCIAL_FEDERATION_HUB_URL:-https://hub.autobrainservice.app}",
            "SOCIAL_FEDERATION_HOSTED: ${SOCIAL_FEDERATION_HOSTED:-false}",
        ],
    ),
]


@pytest.mark.parametrize(
    ("compose_file", "scope_marker", "expected_env"),
    COMPOSE_BACKEND_ENV,
    ids=["hosted", "prod", "dev"],
)
def test_compose_wires_federation_hub_env(compose_file, scope_marker, expected_env) -> None:
    """The 502 regression: backend env must declare the hub URL (non-empty default)."""
    text = (REPO_ROOT / compose_file).read_text()
    if scope_marker in text:
        block = text.split(scope_marker, 1)[1]
    else:
        block = text
    for line in expected_env:
        assert line in block, f"{compose_file} is missing `{line}` in the backend env"


def test_unconfigured_hub_raises_federation_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty SOCIAL_FEDERATION_HUB_URL -> 'hub not configured' -> the 502 users saw."""
    monkeypatch.delenv("SOCIAL_FEDERATION_HUB_URL", raising=False)
    monkeypatch.delenv("SOCIAL_FEDERATION_HOSTED", raising=False)
    config_module.get_settings.cache_clear()
    monkeypatch.setattr(federation, "settings", config_module.get_settings())
    assert federation.settings.SOCIAL_FEDERATION_HUB_URL == ""

    cfg = SocialServerConfig(id=1, server_hub_url=None)
    with pytest.raises(federation.FederationUnavailable, match="hub not configured"):
        federation._hub_url(cfg)


def test_configured_hub_url_is_used() -> None:
    cfg = SocialServerConfig(id=1, server_hub_url="https://hub.example.test")
    assert federation._hub_url(cfg) == "https://hub.example.test"
